<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'

import DOMPurify from 'dompurify'
import * as MarkdownIt from 'markdown-it'

import { getProjectDocsIndex, type ProjectDocsIndexResponse } from '../api/openDeepWiki'

const route = useRoute()
const router = useRouter()

const project = computed(() => String(route.params.project || '').trim())

const loading = ref(false)
const error = ref<string | undefined>(undefined)
const docsIndex = ref<ProjectDocsIndexResponse | null>(null)

const question = ref('')

const MarkdownItCtor: any = (MarkdownIt as any).default ?? (MarkdownIt as any)
const md = new MarkdownItCtor({ linkify: true, breaks: true, html: false })

function getApiBase(): string {
  const base = (import.meta.env.VITE_API_BASE as string | undefined) ?? '/api/v1'
  return base.endsWith('/') ? base.slice(0, -1) : base
}

function rewriteDocLinks(html: string, projectName: string): string {
  const p = encodeURIComponent(String(projectName || '').trim())
  if (!p) return html

  const docsBase = `${getApiBase()}/projects/${p}/docs/`

  // Rewrite relative links in generated markdown so they resolve against the API endpoint.
  // Example: href="features/foo.md" -> href="/api/v1/projects/<p>/docs/features/foo.md"
  return html
    .replace(/href="features\//g, `href="${docsBase}features/`)
    .replace(/href="PROJECT_OVERVIEW\.md"/g, `href="${docsBase}PROJECT_OVERVIEW.md"`)
}

function renderMarkdown(text: string): string {
  const raw = md.render(text ?? '')
  const sanitized = DOMPurify.sanitize(raw)
  return rewriteDocLinks(sanitized, project.value)
}

const overviewHtml = computed(() => renderMarkdown(docsIndex.value?.markdown ?? ''))

async function load(): Promise<void> {
  error.value = undefined
  docsIndex.value = null

  const p = project.value
  if (!p) return

  loading.value = true
  try {
    docsIndex.value = await getProjectDocsIndex(p)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

async function startChat(): Promise<void> {
  const p = project.value
  if (!p) return

  const q = question.value.trim()
  question.value = ''

  await router.push({
    name: 'chat',
    params: { project: p },
    query: q ? { q } : undefined,
  })
}

onMounted(load)
</script>

<template>
  <div class="h-screen w-full overflow-hidden">
    <div class="mx-auto flex h-full w-full max-w-6xl flex-col overflow-hidden px-6 py-6">
      <div class="flex shrink-0 items-center justify-between gap-4">
        <div class="flex items-center gap-3">
          <RouterLink class="text-sm text-slate-600 hover:underline" to="/">← Projects</RouterLink>
          <h1 class="text-lg font-semibold text-slate-900">{{ project }}</h1>
        </div>
      </div>

      <div class="mt-6 flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white">
        <div class="shrink-0 border-b border-slate-200 p-4">
          <div class="text-sm font-semibold text-slate-900">Documentation</div>
          <div class="mt-1 text-xs text-slate-600" v-if="docsIndex?.updated_at">Updated: {{ docsIndex.updated_at }}</div>
        </div>

        <div class="min-h-0 flex-1 overflow-auto p-6">
          <div v-if="loading" class="text-sm text-slate-600">Loading…</div>
          <div v-else-if="error" class="text-sm text-red-700">{{ error }}</div>
          <div v-else-if="!docsIndex?.markdown" class="text-sm text-slate-600">
            No docs yet. Run indexing for this project.
          </div>
          <div v-else class="chat-markdown" v-html="overviewHtml"></div>
        </div>
      </div>

      <!-- Bottom chat start panel -->
      <form class="mt-4 shrink-0 rounded-xl border border-slate-200 bg-white p-4" @submit.prevent="startChat">
        <div class="flex gap-3">
          <input
            v-model="question"
            class="h-11 flex-1 rounded-md border border-slate-200 bg-white px-3 text-slate-900"
            placeholder="Ask a question to start a chat…"
          />
          <button
            type="submit"
            class="h-11 rounded-md bg-slate-900 px-5 text-sm font-medium text-white disabled:opacity-60"
            :disabled="!project"
          >
            Start chat
          </button>
        </div>
      </form>
    </div>
  </div>
</template>
