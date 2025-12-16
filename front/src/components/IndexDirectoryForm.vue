<script setup lang="ts">
import { ref } from 'vue'

import { getIndexStatus, indexDirectory } from '../api/openDeepWiki'

const emit = defineEmits<{
  indexed: []
  indexingStarted: [payload: { project: string; path: string; status: 'in_progress' | 'done' }]
  indexingStatus: [payload: { project: string; status: 'in_progress' | 'done'; error?: string | null }]
}>()

const project = ref('')
const path = ref('')

const loading = ref(false)
const error = ref('')
const success = ref('')
const status = ref<'in_progress' | 'done' | ''>('')

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function pollIndexStatus(project: string): Promise<void> {
  // Poll until the backend reports completion.
  for (let i = 0; i < 60 * 30; i++) {
    // up to ~30 minutes
    const s = await getIndexStatus(project)
    status.value = s.status
    if (s.error) {
      error.value = s.error
    }
    emit('indexingStatus', { project, status: s.status, error: s.error })
    if (s.status === 'done') return
    await sleep(1000)
  }
}

async function onSubmit(): Promise<void> {
  error.value = ''
  success.value = ''
  status.value = ''

  const p = project.value.trim()
  const dir = path.value.trim()
  if (!p || !dir) {
    error.value = 'Project and directory path are required.'
    return
  }

  loading.value = true
  try {
    const started = await indexDirectory({ project: p, path: dir, reindex: false })
    status.value = started.status ?? 'in_progress'
    success.value = `Indexing status: ${status.value}`

    emit('indexingStarted', { project: p, path: dir, status: status.value || 'in_progress' })

    if (status.value === 'in_progress') {
      await pollIndexStatus(p)
    }

    success.value = 'Indexing status: done'
    emit('indexed')
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <form class="w-full max-w-2xl" @submit.prevent="onSubmit">
    <div class="grid gap-3 sm:grid-cols-2">
      <label class="grid gap-1 text-left text-sm">
        <span class="font-medium">Project name</span>
        <input
          v-model="project"
          class="h-10 rounded-md border border-slate-200 bg-white px-3 text-slate-900"
          placeholder="my-project"
          :disabled="loading"
        />
      </label>

      <label class="grid gap-1 text-left text-sm">
        <span class="font-medium">Directory to index</span>
        <input
          v-model="path"
          class="h-10 rounded-md border border-slate-200 bg-white px-3 text-slate-900"
          placeholder="/abs/path/to/java/code"
          :disabled="loading"
        />
      </label>
    </div>

    <div class="mt-3 flex items-center gap-3">
      <button
        type="submit"
        class="h-10 rounded-md bg-slate-900 px-4 text-sm font-medium text-white disabled:opacity-60"
        :disabled="loading"
      >
        {{ loading ? 'Indexing…' : 'Index project' }}
      </button>

      <p v-if="error" class="text-sm text-red-700">{{ error }}</p>
      <p v-else-if="success" class="text-sm text-green-700">{{ success }}</p>
    </div>

    <p v-if="status" class="mt-2 text-left text-sm text-slate-700">Status: {{ status }}</p>
  </form>
</template>
