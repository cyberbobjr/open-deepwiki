<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { RouterLink } from 'vue-router'

import { getIndexStatus, type DeleteProjectResponse, type ProjectInfo } from '../api/openDeepWiki'
import ConfirmModal from '../components/ConfirmModal.vue'
import IndexDirectoryForm from '../components/IndexDirectoryForm.vue'
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

const indexingByProject = ref<Record<string, 'in_progress' | 'done'>>({})

function isIndexing(project: string): boolean {
  return indexingByProject.value[project] === 'in_progress'
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
    indexingByProject.value[p] = s.status
  } catch {
    // Keep previous status if the status endpoint is unavailable.
  }
}

let pollingTimer: number | null = null

function startPollingIndexing(): void {
  if (pollingTimer !== null) return
  pollingTimer = window.setInterval(async () => {
    const inProgress = Object.entries(indexingByProject.value)
      .filter(([, status]) => status === 'in_progress')
      .map(([project]) => project)

    if (inProgress.length === 0) return

    for (const p of inProgress) {
      await refreshIndexingStatusFor(p)
      if (!isIndexing(p)) {
        await projectsStore.refresh()
      }
    }
  }, 2000)
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
  <div class="mx-auto w-full max-w-6xl px-6 py-10">
    <ConfirmModal
      :open="modalOpen"
      :mode="modalMode"
      :title="modalTitle"
      :message="modalMessage"
      confirmText="Delete"
      cancelText="Cancel"
      :busy="projectsStore.deletingProject === pendingDeleteProject"
      @cancel="cancelDeleteProject"
      @confirm="confirmDeleteProject"
    />

    <div class="flex flex-col gap-2">
      <h1 class="text-2xl font-semibold text-slate-900">open-deepwiki</h1>
      <p class="text-slate-600">Select a project to start a conversation, or index a new directory.</p>
    </div>

    <div class="mt-6">
      <IndexDirectoryForm
        @indexingStarted="(e) => {
          upsertProject({ project: e.project, indexed_path: e.path, indexed_at: null })
          indexingByProject[e.project] = e.status
          startPollingIndexing()
        }"
        @indexingStatus="(e) => {
          indexingByProject[e.project] = e.status
        }"
        @indexed="projectsStore.refresh()"
      />
    </div>

    <div class="mt-10">
      <div class="flex items-center justify-between">
        <h2 class="text-lg font-semibold text-slate-900">Projects</h2>
        <button
          class="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900 disabled:opacity-60"
          :disabled="projectsStore.loading"
          @click="projectsStore.refresh()"
        >
          Refresh
        </button>
      </div>

      <p v-if="projectsStore.error" class="mt-3 text-sm text-red-700">{{ projectsStore.error }}</p>
      <p v-else-if="projectsStore.loading" class="mt-3 text-sm text-slate-600">Loading…</p>

      <div v-else class="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div
          v-for="p in projectsStore.projects"
          :key="p.project"
          class="group relative min-h-40 rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition"
          :class="isIndexing(p.project) ? 'opacity-60' : 'hover:border-slate-300'"
        >
          <RouterLink
            v-if="!isIndexing(p.project)"
            :to="{ name: 'project', params: { project: p.project } }"
            class="block h-full"
          >
            <div class="flex h-full flex-col justify-between gap-3">
              <div class="text-center">
                <div class="text-base font-medium text-slate-900 group-hover:underline">{{ p.project }}</div>
              </div>

              <div class="text-xs text-slate-600">
                <div class="truncate" v-if="p.indexed_path" :title="p.indexed_path">{{ p.indexed_path }}</div>
                <div v-if="p.indexed_at">Indexed: {{ p.indexed_at }}</div>
                <div v-if="!p.indexed_at" class="text-slate-500">Indexed: unknown</div>
              </div>
            </div>
          </RouterLink>

          <div v-else class="flex h-full flex-col justify-between gap-3" aria-disabled="true">
            <div class="text-center">
              <div class="text-base font-medium text-slate-900">{{ p.project }}</div>
              <div class="mt-3 flex items-center justify-center gap-2 text-sm text-slate-600">
                <div class="h-5 w-5 animate-spin rounded-full border-2 border-slate-300 border-t-slate-900" />
                <span>Indexing…</span>
              </div>
            </div>

            <div class="text-xs text-slate-600">
              <div class="truncate" v-if="p.indexed_path" :title="p.indexed_path">{{ p.indexed_path }}</div>
              <div class="text-slate-500">Indexed: pending</div>
            </div>
          </div>

          <button
            class="absolute right-3 top-3 h-8 rounded-md border border-slate-200 bg-white px-2 text-xs text-red-700 disabled:opacity-60"
            :disabled="projectsStore.loading || projectsStore.deletingProject === p.project || isIndexing(p.project)"
            @click.prevent.stop="requestDeleteProject(p.project)"
            title="Delete project"
          >
            {{ projectsStore.deletingProject === p.project ? 'Deleting…' : 'Delete' }}
          </button>
        </div>

        <div
          v-if="projectsStore.projects.length === 0"
          class="col-span-full rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center text-slate-600"
        >
          No projects indexed yet.
        </div>
      </div>
    </div>
  </div>
</template>
