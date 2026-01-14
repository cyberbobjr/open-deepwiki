<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

import { getIndexStatus, regenerateDocumentation, type DeleteProjectResponse, type ProjectInfo } from '../api/openDeepWiki'
import ConfirmModal from '../components/ConfirmModal.vue'
import IndexDirectoryForm from '../components/IndexDirectoryForm.vue'
import ProjectCard from '../components/ProjectCard.vue'
import { useProjectsStore } from '../stores/projects'

const projectsStore = useProjectsStore()

const pendingDeleteProject = ref<string | null>(null)
const deleteResult = ref<DeleteProjectResponse | null>(null)

const modalOpen = computed(() => pendingDeleteProject.value !== null || deleteResult.value !== null)
const modalMode = computed<'confirm' | 'info'>(() => (deleteResult.value ? 'info' : 'confirm'))

const modalTitle = computed(() => {
  if (deleteResult.value) return `Deleted ${deleteResult.value.project}`
  const p = pendingDeleteProject.value
  return p ? `Delete ${p}?` : 'Delete project?'
})

const modalMessage = computed(() => {
  if (deleteResult.value) {
    const r = deleteResult.value
    const yesNo = (v: boolean | undefined): string => (v === undefined ? 'unknown' : v ? 'yes' : 'no')

    return [
      `Deleted: ${yesNo(r.deleted)}`,
      `Vectorstore docs: ${yesNo(r.deleted_vectorstore_docs)}`,
      `Graph: ${yesNo(r.deleted_graph)}`,
      `Sessions deleted: ${r.deleted_sessions ?? 0}`,
      `Output dir deleted: ${yesNo(r.deleted_output_dir)}`,
    ].join('\n')
  }

  const p = pendingDeleteProject.value
  if (!p) return ''

  const base = `This will remove indexed docs, graph data, sessions, and generated OUTPUT docs for "${p}".`
  if (!projectsStore.error) return base
  return `${base}\n\nError: ${projectsStore.error}`
})

type IndexingState = {
  status: 'in_progress' | 'done'
  step?: string
  details?: string
}

const indexingByProject = ref<Record<string, IndexingState>>({})

function isIndexing(project: string): boolean {
  return indexingByProject.value[project]?.status === 'in_progress'
}

function upsertProject(project: ProjectInfo): void {
  const idx = projectsStore.projects.findIndex((p) => p.project === project.project)
  if (idx >= 0) {
    projectsStore.projects[idx] = { ...projectsStore.projects[idx], ...project }
  } else {
    projectsStore.projects.unshift(project)
  }
}

async function refreshIndexingStatusFor(project: string): Promise<void> {
  const p = project.trim()
  if (!p) return
  try {
    const s = await getIndexStatus(p)
    indexingByProject.value[p] = {
      status: s.status,
      step: s.step ?? undefined,
      details: s.details ?? undefined,
    }
  } catch {
    // Keep previous status if the status endpoint is unavailable.
  }
}

let pollingTimer: number | null = null

function startPollingIndexing(): void {
  if (pollingTimer !== null) return
  pollingTimer = window.setInterval(async () => {
    const inProgress = Object.entries(indexingByProject.value)
      .filter(([, state]) => state.status === 'in_progress')
      .map(([project]) => project)

    if (inProgress.length === 0) return

    for (const p of inProgress) {
      await refreshIndexingStatusFor(p)
      if (!isIndexing(p)) {
        await projectsStore.refresh()
      }
    }
  }, 5000)
}

function stopPollingIndexing(): void {
  if (pollingTimer === null) return
  window.clearInterval(pollingTimer)
  pollingTimer = null
}

function requestDeleteProject(project: string): void {
  const p = project.trim()
  if (!p) return
  deleteResult.value = null
  pendingDeleteProject.value = p
}

async function onRegenerate(project: string): Promise<void> {
  const p = project.trim()
  if (!p) return
  try {
    const res = await regenerateDocumentation({ project: p })
    indexingByProject.value[p] = { status: res.status }
    startPollingIndexing()
  } catch (err: any) {
    console.error(err)
    alert(`Failed to start regeneration: ${err.message}`)
  }
}

function cancelDeleteProject(): void {
  if (deleteResult.value) {
    deleteResult.value = null
    return
  }
  pendingDeleteProject.value = null
}

async function confirmDeleteProject(): Promise<void> {
  const p = pendingDeleteProject.value
  if (!p) return

  const res = await projectsStore.removeProject(p)
  if (!res) return

  deleteResult.value = res
  pendingDeleteProject.value = null
}

onMounted(async () => {
  await projectsStore.refresh()
  for (const p of projectsStore.projects) {
    await refreshIndexingStatusFor(p.project)
  }
  startPollingIndexing()
})

onUnmounted(() => {
  stopPollingIndexing()
})
</script>

<template>
  <div class="w-full px-6 py-10">
    <ConfirmModal :open="modalOpen" :mode="modalMode" :title="modalTitle" :message="modalMessage" confirmText="Delete"
      cancelText="Cancel" :busy="projectsStore.deletingProject === pendingDeleteProject" @cancel="cancelDeleteProject"
      @confirm="confirmDeleteProject" />

    <div class="flex flex-col gap-2">
      <h1 class="text-2xl font-semibold text-slate-900">open-deepwiki</h1>
      <p class="text-slate-600">Select a project to start a conversation, or index a new directory.</p>
    </div>

    <div class="mt-6">
      <IndexDirectoryForm @indexingStarted="(e) => {
        upsertProject({ project: e.project, indexed_path: e.path, indexed_at: null })
        indexingByProject[e.project] = { status: e.status }
        startPollingIndexing()
      }" @indexingStatus="(e) => {
        indexingByProject[e.project] = {
          status: e.status,
          step: e.step ?? undefined,
          details: e.details ?? undefined
        }
      }" @indexed="projectsStore.refresh()" />
    </div>

    <div class="mt-10">
      <div class="flex items-center justify-between">
        <h2 class="text-lg font-semibold text-slate-900">Projects</h2>
        <button class="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900 disabled:opacity-60"
          :disabled="projectsStore.loading" @click="projectsStore.refresh()">
          Refresh
        </button>
      </div>

      <p v-if="projectsStore.error" class="mt-3 text-sm text-red-700">{{ projectsStore.error }}</p>
      <p v-else-if="projectsStore.loading" class="mt-3 text-sm text-slate-600">Loading…</p>

      <div v-else class="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <ProjectCard v-for="p in projectsStore.projects" :key="p.project" :project="p"
          :is-indexing="isIndexing(p.project)" :indexing-step="indexingByProject[p.project]?.step"
          :indexing-details="indexingByProject[p.project]?.details"
          :is-deleting="projectsStore.deletingProject === p.project" @delete="requestDeleteProject"
          @regenerate="onRegenerate" />

        <div v-if="projectsStore.projects.length === 0"
          class="col-span-full rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center text-slate-600">
          No projects indexed yet.
        </div>
      </div>
    </div>
  </div>
</template>
