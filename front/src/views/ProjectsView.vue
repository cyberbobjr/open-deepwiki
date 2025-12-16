<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'

import type { DeleteProjectResponse } from '../api/openDeepWiki'
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
      <IndexDirectoryForm @indexed="projectsStore.refresh()" />
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
          class="group relative aspect-square rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition hover:border-slate-300"
        >
          <RouterLink
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

          <button
            class="absolute right-3 top-3 h-8 rounded-md border border-slate-200 bg-white px-2 text-xs text-red-700 disabled:opacity-60"
            :disabled="projectsStore.loading || projectsStore.deletingProject === p.project"
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
