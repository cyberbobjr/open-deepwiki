<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'

import DOMPurify from 'dompurify'
import * as MarkdownIt from 'markdown-it'

import { useChatStore } from '../stores/chat'
import type { QueryResult } from '../api/openDeepWiki'

const route = useRoute()
const router = useRouter()
const project = computed(() => String(route.params.project || '').trim())
const overviewTo = computed(() => ({ name: 'project', params: { project: project.value } }))

const chat = useChatStore()
const thread = computed(() => chat.getThread(project.value))

const question = ref('')
const k = ref(4)

const messagesEl = ref<HTMLElement | null>(null)

const MarkdownItCtor: any = (MarkdownIt as any).default ?? (MarkdownIt as any)
const md = new MarkdownItCtor({ linkify: true, breaks: true, html: false })

function renderMarkdown(text: string): string {
  const raw = md.render(text ?? '')
  return DOMPurify.sanitize(raw)
}

const selectedContextIndex = ref(0)

async function sendText(text: string): Promise<void> {
  const q = String(text || '').trim()
  if (!q || thread.value.loading) return

  await chat.sendQuestionStreamed(project.value, q, k.value)

  await nextTick()
  messagesEl.value?.scrollTo({ top: messagesEl.value.scrollHeight, behavior: 'smooth' })
}

async function send(): Promise<void> {
  const q = question.value
  question.value = ''
  await sendText(q)
}

watch(
  () => thread.value.context,
  (ctx) => {
    if (ctx && ctx.length > 0) selectedContextIndex.value = 0
  },
)

const selectedContext = computed<QueryResult | undefined>(() => {
  const ctx: QueryResult[] = thread.value.context ?? []
  const idx = Math.max(0, Math.min(selectedContextIndex.value, ctx.length - 1))
  return ctx[idx]
})

const contexts = computed<QueryResult[]>(() => thread.value.context ?? [])

const messages = computed(() => thread.value.messages ?? [])

function fileNameFromPath(pathValue: string): string {
  const p = String(pathValue || '').trim()
  if (!p) return ''
  const parts = p.split('/')
  return parts[parts.length - 1] ?? p
}

function extractCodeFromPageContent(pageContent: string): string {
  const text = String(pageContent || '')
  const marker = "\n\nCode:\n"
  const idx = text.indexOf(marker)
  if (idx >= 0) return text.slice(idx + marker.length)
  const marker2 = "\nCode:\n"
  const idx2 = text.indexOf(marker2)
  if (idx2 >= 0) return text.slice(idx2 + marker2.length)
  return text
}

function contextTitle(c: QueryResult | undefined): string {
  return String(c?.signature || c?.id || 'context')
}

function contextLocation(c: QueryResult | undefined): string {
  const fp = String(c?.file_path || '').trim()
  const start = Number(c?.start_line)
  const end = Number(c?.end_line)
  const hasStart = Number.isFinite(start) && start > 0
  const hasEnd = Number.isFinite(end) && end > 0

  const locParts: string[] = []
  if (fp) locParts.push(fp)
  if (hasStart && hasEnd) locParts.push(`L${start}-L${end}`)
  else if (hasStart) locParts.push(`L${start}`)

  return locParts.join(' · ')
}

watch(
  () => project.value,
  async () => {
    await nextTick()
    messagesEl.value?.scrollTo({ top: messagesEl.value.scrollHeight })
  },
  { immediate: true },
)

async function startFromQueryIfNeeded(): Promise<void> {
  const q = route.query.q
  if (typeof q !== 'string' || !q.trim()) return

  // Clear the query param so refresh doesn't re-run the first prompt.
  await router.replace({ name: 'chat', params: { project: project.value }, query: {} })
  await sendText(q)
}

onMounted(startFromQueryIfNeeded)
</script>

<template>
  <div class="h-screen w-full overflow-hidden">
    <div class="mx-auto flex h-full w-full max-w-6xl flex-col overflow-hidden px-6 py-6">
      <div class="flex shrink-0 items-center justify-between gap-4">
        <div class="flex items-center gap-3">
          <RouterLink class="text-sm text-slate-600 hover:underline" :to="overviewTo">
            ← Overview
          </RouterLink>
          <h1 class="text-lg font-semibold text-slate-900">{{ project }}</h1>
        </div>
        <div class="text-xs text-slate-500" v-if="thread.sessionId">Session: {{ thread.sessionId }}</div>
      </div>

      <div class="mt-6 flex min-h-0 flex-1 overflow-hidden gap-4">
        <!-- Left: conversation -->
        <section class="flex min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white">
          <div class="border-b border-slate-200 p-4">
            <div class="text-sm font-semibold text-slate-900">Conversation</div>
          </div>

          <div ref="messagesEl" class="min-h-0 flex-1 overflow-auto p-6">
            <div v-if="messages.length === 0" class="text-sm text-slate-600">Start by asking a question.</div>

            <div v-else class="flex flex-col gap-4">
              <div v-for="(m, idx) in messages" :key="idx" class="flex">
                <div
                  class="max-w-3xl rounded-lg border border-slate-200 px-3 py-2 text-sm"
                  :class="m.role === 'user' ? 'ml-auto bg-slate-50 text-slate-900' : 'mr-auto bg-white text-slate-900'"
                >
                  <div v-if="m.role === 'assistant'" class="chat-markdown" v-html="renderMarkdown(m.content)"></div>
                  <div v-else class="whitespace-pre-wrap">{{ m.content }}</div>
                </div>
              </div>
            </div>

            <div v-if="contexts.length > 0" class="mt-8">
              <div class="text-xs font-semibold text-slate-700">File references</div>
              <div class="mt-3 flex flex-col gap-2">
                <button
                  v-for="(c, idx) in contexts"
                  :key="idx"
                  type="button"
                  class="flex items-center justify-between gap-3 rounded-md border border-slate-200 bg-white px-3 py-2 text-left"
                  :class="idx === selectedContextIndex ? 'border-slate-900' : ''"
                  @click="selectedContextIndex = idx"
                >
                  <div class="min-w-0">
                    <div class="truncate text-sm font-medium text-slate-900" :title="contextTitle(c)">
                      {{ contextTitle(c) }}
                    </div>
                    <div class="truncate text-xs text-slate-600" :title="contextLocation(c)">
                      {{ contextLocation(c) || 'unknown location' }}
                    </div>
                  </div>
                  <div class="text-xs text-slate-500">Preview</div>
                </button>
              </div>
            </div>

            <p v-if="thread.error" class="mt-4 text-sm text-red-700">{{ thread.error }}</p>
          </div>

          <!-- Bottom input (pinned) -->
          <form class="shrink-0 border-t border-slate-200 bg-white p-4" @submit.prevent="send">
            <div class="grid gap-3">
              <div class="flex items-center justify-between gap-3">
                <label class="flex items-center gap-2 text-sm text-slate-700">
                  <span>K</span>
                  <input
                    v-model.number="k"
                    type="number"
                    min="1"
                    max="50"
                    class="h-9 w-20 rounded-md border border-slate-200 bg-white px-2 text-slate-900"
                    :disabled="thread.loading"
                  />
                </label>
              </div>

              <div class="flex gap-3">
                <input
                  v-model="question"
                  class="h-11 flex-1 rounded-md border border-slate-200 bg-white px-3 text-slate-900"
                  placeholder="Ask a follow-up question…"
                  :disabled="thread.loading"
                />
                <button
                  type="submit"
                  class="h-11 rounded-md bg-slate-900 px-5 text-sm font-medium text-white disabled:opacity-60"
                  :disabled="thread.loading || !question.trim()"
                >
                  {{ thread.loading ? 'Streaming…' : 'Send' }}
                </button>
              </div>
            </div>
          </form>
        </section>

        <!-- Right: preview -->
        <aside class="flex w-96 shrink-0 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white">
          <div class="border-b border-slate-200 p-4">
            <div class="text-sm font-semibold text-slate-900">Code</div>
            <div v-if="selectedContext" class="mt-1 text-xs text-slate-600">
              {{ contextLocation(selectedContext) || 'No file information for this snippet.' }}
            </div>
          </div>

          <div class="border-b border-slate-200 px-2 py-2">
            <div class="flex gap-2 overflow-auto">
              <button
                v-for="(c, idx) in contexts"
                :key="idx"
                type="button"
                class="shrink-0 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-900"
                :class="idx === selectedContextIndex ? 'border-slate-900 font-semibold' : ''"
                @click="selectedContextIndex = idx"
                :title="contextLocation(c)"
              >
                {{ fileNameFromPath(String(c.file_path || 'snippet')) || 'snippet' }}
              </button>
            </div>
          </div>

          <div class="min-h-0 flex-1 overflow-auto p-4">
            <div v-if="!selectedContext" class="text-sm text-slate-600">Select a source to preview code.</div>
            <div v-else>
              <pre class="whitespace-pre-wrap text-xs text-slate-900">{{ extractCodeFromPageContent(selectedContext.page_content) }}</pre>
            </div>
          </div>
        </aside>
      </div>
    </div>
  </div>
</template>
