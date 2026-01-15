<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import DOMPurify from 'dompurify'
import * as MarkdownIt from 'markdown-it'

import { installMermaidFence } from '../utils/mermaid'

import ConfirmModal from '../components/ConfirmModal.vue'
import ChatContextPanel, { type FileContextGroup } from '../components/chat/ChatContextPanel.vue'
import ChatPanel from '../components/chat/ChatPanel.vue'
// Spinner removed as it is now in ChatPanel
import type { QueryResult } from '../api/openDeepWiki'
import { useChatStore } from '../stores/chat'

const route = useRoute()
const router = useRouter()
const project = computed(() => String(route.params.project || '').trim())
const overviewTo = computed(() => ({ name: 'project', params: { project: project.value } }))

const chat = useChatStore()
const thread = computed(() => chat.getThread(project.value))

const question = ref('')
const k = ref(4)

const chatPanelRef = ref<InstanceType<typeof ChatPanel> | null>(null)

const MarkdownItCtor: any = (MarkdownIt as any).default ?? (MarkdownIt as any)
const md = new MarkdownItCtor({ linkify: true, breaks: true, html: false })
installMermaidFence(md)

type TocItem = {
  id: string
  text: string
  level: number
}

function getApiBase(): string {
  const base = (import.meta.env.VITE_API_BASE as string | undefined) ?? '/api/v1'
  return base.endsWith('/') ? base.slice(0, -1) : base
}

function slugifyHeading(text: string): string {
  const base = String(text || '')
    .trim()
    .toLowerCase()
    .replace(/[`*_~]/g, '')
    .replace(/[^a-z0-9\s-]/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')

  return base || 'section'
}

function renderMarkdownWithToc(markdown: string): { html: string; toc: TocItem[] } {
  const rawHtml = md.render(markdown ?? '')

  const container = document.createElement('div')
  container.innerHTML = rawHtml

  const headings = Array.from(container.querySelectorAll('h1,h2,h3,h4,h5,h6')) as HTMLHeadingElement[]
  const seen: Record<string, number> = {}
  const items: TocItem[] = []

  for (const h of headings) {
    const text = String(h.textContent || '').trim()
    if (!text) continue

    const base = slugifyHeading(text)
    const n = (seen[base] ?? 0) + 1
    seen[base] = n
    const id = n === 1 ? base : `${base}-${n}`

    h.id = id

    const level = Number(String(h.tagName || '').replace(/[^0-9]/g, '')) || 2
    items.push({ id, text, level })
  }

  const sanitized = DOMPurify.sanitize(container.innerHTML)
  return { html: sanitized, toc: items }
}

function extractAnchorHref(evt: MouseEvent): string | undefined {
  const target = evt.target as HTMLElement | null
  if (!target) return
  const a = target.closest('a') as HTMLAnchorElement | null
  if (!a) return
  const href = String(a.getAttribute('href') || '').trim()
  return href || undefined
}

function isMarkdownDocLink(href: string): boolean {
  const h = String(href || '').trim()
  if (!h) return false
  if (h.startsWith('#')) return false

  // Treat API docs links and direct markdown links as in-app docs.
  if (h.includes('/docs/') && h.includes('.md')) return true
  if (h.endsWith('.md')) return true
  if (h.includes('.md#')) return true
  return false
}

function resolveDocsUrl(href: string, baseUrl: string): string {
  const h = String(href || '').trim()
  if (!h) return ''

  // Already absolute (http/https)
  if (/^https?:\/\//i.test(h)) return h

  // Already absolute path (e.g. /api/v1/...)
  if (h.startsWith('/')) return h

  // Resolve relative against a base URL (used for nested docs).
  try {
    const base = /^https?:\/\//i.test(baseUrl)
      ? baseUrl
      : new URL(baseUrl, window.location.origin).toString()
    return new URL(h, base).toString()
  } catch {
    return h
  }
}

function splitMarkdownHref(href: string): { url: string; hash?: string } {
  const h = String(href || '')
  const idx = h.indexOf('#')
  if (idx < 0) return { url: h }
  const url = h.slice(0, idx)
  const hash = h.slice(idx + 1)
  return { url: url || h, hash: hash || undefined }
}





const docOpen = ref(false)
const docLoading = ref(false)
const docError = ref<string | undefined>(undefined)
const docUrl = ref<string | undefined>(undefined)
const docTitle = ref<string>('')
const docContextPanelRef = ref<InstanceType<typeof ChatContextPanel> | null>(null)
const docRenderedHtml = ref('')
const docToc = ref<TocItem[]>([])

const detailsHidden = ref(false)

function toggleDetailsHidden(): void {
  detailsHidden.value = !detailsHidden.value
}

const pendingDeleteSessionId = ref<string | null>(null)
const deletingSession = ref(false)

const deleteSessionModalOpen = computed(() => pendingDeleteSessionId.value !== null)

const deleteSessionModalMessage = computed(() => {
  const id = pendingDeleteSessionId.value
  if (!id) return ''
  const base = `This will delete the server-side conversation session: ${id}`
  if (!thread.value.error) return base
  return `${base}\n\nError: ${thread.value.error}`
})

function docsBaseForProject(projectName: string): string {
  const p = encodeURIComponent(String(projectName || '').trim())
  return `${getApiBase()}/projects/${p}/docs/`
}

function fileNameFromUrl(url: string | undefined): string {
  const u = String(url || '').trim()
  if (!u) return ''
  const noHash = u.split('#')[0] ?? u
  const parts = noHash.split('/')
  return decodeURIComponent(parts[parts.length - 1] || noHash)
}

function scrollToDocHeading(id: string): void {
  docContextPanelRef.value?.scrollToHeading(id)
}

async function openMarkdownDoc(urlInput: string, opts?: { hash?: string }): Promise<void> {
  const url = String(urlInput || '').trim()
  if (!url) return

  docOpen.value = true
  docLoading.value = true
  docError.value = undefined
  docUrl.value = url
  docTitle.value = fileNameFromUrl(url)

  try {
    const res = await fetch(url)
    if (!res.ok) {
      const text = await res.text().catch(() => '')
      throw new Error(text || `Failed to load markdown: ${res.status} ${res.statusText}`)
    }

    const markdown = await res.text()
    const rendered = renderMarkdownWithToc(markdown)
    docRenderedHtml.value = rendered.html
    docToc.value = rendered.toc

    if (opts?.hash) {
      await nextTick()
      const hash = String(opts.hash || '').trim()
      if (hash) scrollToDocHeading(hash)
    }
  } catch (e) {
    docError.value = e instanceof Error ? e.message : String(e)
    docRenderedHtml.value = ''
    docToc.value = []
  } finally {
    docLoading.value = false
  }
}

function closeMarkdownDoc(): void {
  docOpen.value = false
  docLoading.value = false
  docError.value = undefined
  docUrl.value = undefined
  docTitle.value = ''
  docRenderedHtml.value = ''
  docToc.value = []
}

function onAssistantMarkdownClick(evt: MouseEvent): void {
  const href = extractAnchorHref(evt)
  if (!href) return

  // Keep external links from navigating away.
  if (/^https?:\/\//i.test(href) && !isMarkdownDocLink(href)) {
    evt.preventDefault()
    window.open(href, '_blank', 'noopener')
    return
  }

  if (!isMarkdownDocLink(href)) return
  evt.preventDefault()

  const base = docsBaseForProject(project.value)
  const parts = splitMarkdownHref(href)
  const resolved = resolveDocsUrl(parts.url, base)
  openMarkdownDoc(resolved, { hash: parts.hash })
}

function onDocMarkdownClick(evt: MouseEvent): void {
  const href = extractAnchorHref(evt)
  if (!href) return

  // In-document anchors scroll within the document panel.
  if (href.startsWith('#')) {
    evt.preventDefault()
    scrollToDocHeading(href.slice(1))
    return
  }

  const current = String(docUrl.value || '').trim()
  const baseUrl = current ? current.replace(/[^/]+$/, '') : docsBaseForProject(project.value)

  // Keep external links from navigating away.
  if (/^https?:\/\//i.test(href) && !isMarkdownDocLink(href)) {
    evt.preventDefault()
    window.open(href, '_blank', 'noopener')
    return
  }

  if (!isMarkdownDocLink(href)) return
  evt.preventDefault()

  const parts = splitMarkdownHref(href)
  const resolved = resolveDocsUrl(parts.url, baseUrl)
  openMarkdownDoc(resolved, { hash: parts.hash })
}

async function sendText(text: string): Promise<void> {
  const q = String(text || '').trim()
  if (!q || thread.value.loading) return

  await chat.sendQuestionStreamed(project.value, q, k.value)

  await nextTick()
  if (chatPanelRef.value) {
    chatPanelRef.value.scrollToBottom()
  }
}

async function send(): Promise<void> {
  const q = question.value
  question.value = ''
  await sendText(q)
}

function requestDeleteCurrentSession(): void {
  const id = String(thread.value.sessionId ?? '').trim()
  if (!id) return
  thread.value.error = undefined
  pendingDeleteSessionId.value = id
}

function cancelDeleteSession(): void {
  pendingDeleteSessionId.value = null
}

async function confirmDeleteSession(): Promise<void> {
  const id = pendingDeleteSessionId.value
  if (!id) return
  deletingSession.value = true
  try {
    await chat.deleteSession(project.value, id)
    if (!thread.value.error) pendingDeleteSessionId.value = null
  } finally {
    deletingSession.value = false
  }
}

const messages = computed(() => thread.value.messages ?? [])

// Messages watcher removed as it is handled in ChatPanel

// Watcher removed as specialized component handles it

const contexts = computed<QueryResult[]>(() => thread.value.context ?? [])

const fileContextGroups = computed<FileContextGroup[]>(() => {
  const out: FileContextGroup[] = []
  const indexByPath = new Map<string, number>()

  for (const c of contexts.value) {
    const fp = String(c?.file_path ?? '').trim() || 'snippet'
    const existing = indexByPath.get(fp)
    if (existing === undefined) {
      indexByPath.set(fp, out.length)
      out.push({ filePath: fp, items: [c] })
    } else {
      out[existing]?.items.push(c)
    }
  }

  return out
})


// contextLocation moved to component

watch(
  () => project.value,
  async () => {
    await nextTick()
    chatPanelRef.value?.scrollToBottom()
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


// End of script setup
</script>

<template>
  <div class="h-full w-full overflow-hidden">
    <ConfirmModal :open="deleteSessionModalOpen" mode="confirm" title="Delete this session?"
      :message="deleteSessionModalMessage" confirmText="Delete" cancelText="Cancel" :busy="deletingSession"
      @cancel="cancelDeleteSession" @confirm="confirmDeleteSession" />

    <div class="flex h-full w-full flex-col overflow-hidden px-6 py-6">
      <div class="flex shrink-0 items-center justify-between gap-4">
        <div class="flex items-center gap-3">
          <RouterLink class="text-sm text-slate-600 hover:underline" :to="overviewTo">
            ← Overview
          </RouterLink>
          <h1 class="text-lg font-semibold text-slate-900">{{ project }}</h1>
        </div>
        <div class="flex items-center gap-3">
          <button type="button" class="h-8 rounded-md border border-slate-200 bg-white px-2 text-xs text-slate-700"
            @click="toggleDetailsHidden">
            {{ detailsHidden ? 'Show details' : 'Focus chat' }}
          </button>

          <template v-if="thread.sessionId">
            <div class="text-xs text-slate-500">Session: {{ thread.sessionId }}</div>
            <button type="button" class="h-8 rounded-md border border-slate-200 bg-white px-2 text-xs text-slate-700"
              @click="requestDeleteCurrentSession">
              Delete session
            </button>
          </template>
        </div>
      </div>

      <div class="mt-6 flex min-h-0 flex-1 flex-col gap-4 overflow-hidden lg:flex-row">
        <!-- Left: conversation (~40%) -->
        <ChatPanel ref="chatPanelRef" :messages="messages" :loading="thread.loading" :error="thread.error"
          :details-hidden="detailsHidden" v-model:k="k" v-model:question="question" @send="send"
          @link-click="onAssistantMarkdownClick" />

        <!-- Right: details (remaining space) -->
        <ChatContextPanel ref="docContextPanelRef" :details-hidden="detailsHidden"
          :file-context-groups="fileContextGroups" :doc-open="docOpen" :doc-loading="docLoading" :doc-error="docError"
          :doc-title="docTitle" :doc-url="docUrl" :doc-rendered-html="docRenderedHtml" @close-doc="closeMarkdownDoc"
          @doc-click="onDocMarkdownClick" />
      </div>
    </div>
  </div>
</template>
