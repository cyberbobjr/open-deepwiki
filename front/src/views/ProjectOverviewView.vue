<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
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

type TocItem = {
  id: string
  text: string
  level: number
}

const contentEl = ref<HTMLElement | null>(null)
const renderedHtml = ref('')
const toc = ref<TocItem[]>([])

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

function isMarkdownDocLink(href: string): boolean {
  const h = String(href || '').trim()
  if (!h) return false
  if (h.startsWith('#')) return false
  if (h.includes('/docs/') && h.includes('.md')) return true
  if (h.endsWith('.md')) return true
  if (h.includes('.md#')) return true
  return false
}

function splitMarkdownHref(href: string): { url: string; hash?: string } {
  const h = String(href || '')
  const idx = h.indexOf('#')
  if (idx < 0) return { url: h }
  const url = h.slice(0, idx)
  const hash = h.slice(idx + 1)
  return { url: url || h, hash: hash || undefined }
}

function resolveDocsUrl(href: string, baseUrl: string): string {
  const h = String(href || '').trim()
  if (!h) return ''
  if (/^https?:\/\//i.test(h)) return h
  if (h.startsWith('/')) return h

  try {
    const base = /^https?:\/\//i.test(baseUrl)
      ? baseUrl
      : new URL(baseUrl, window.location.origin).toString()
    return new URL(h, base).toString()
  } catch {
    return h
  }
}

function docsBaseForProject(projectName: string): string {
  const p = encodeURIComponent(String(projectName || '').trim())
  return `${getApiBase()}/projects/${p}/docs/`
}

async function loadDocFromUrl(url: string, opts?: { hash?: string }): Promise<void> {
  const u = String(url || '').trim()
  if (!u) return

  const res = await fetch(u)
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(text || `Failed to load markdown: ${res.status} ${res.statusText}`)
  }

  const text = await res.text()
  const rendered = renderMarkdownWithToc(text)
  renderedHtml.value = rendered.html
  toc.value = rendered.toc

  const hash = String(opts?.hash ?? '').trim()
  if (!hash) return
  requestAnimationFrame(() => scrollToHeading(hash))
}

function onMarkdownClick(evt: MouseEvent): void {
  const target = evt.target as HTMLElement | null
  if (!target) return
  const a = target.closest('a') as HTMLAnchorElement | null
  if (!a) return
  const href = String(a.getAttribute('href') || '').trim()
  if (!href) return

  // Keep external links from navigating away.
  if (/^https?:\/\//i.test(href) && !isMarkdownDocLink(href)) {
    evt.preventDefault()
    window.open(href, '_blank', 'noopener')
    return
  }

  if (!isMarkdownDocLink(href)) return
  evt.preventDefault()

  const parts = splitMarkdownHref(href)
  const base = docsBaseForProject(project.value)
  const resolved = resolveDocsUrl(parts.url, base)

  loadDocFromUrl(resolved, { hash: parts.hash }).catch((e) => {
    error.value = e instanceof Error ? e.message : String(e)
  })
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
  const rewritten = rewriteDocLinks(rawHtml, project.value)

  // Build a DOM so we can assign ids to headings and produce a TOC.
  const container = document.createElement('div')
  container.innerHTML = rewritten

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

function tocIndentClass(level: number): string {
  if (level <= 2) return ''
  if (level === 3) return 'pl-3'
  if (level === 4) return 'pl-6'
  return 'pl-9'
}

function scrollToHeading(id: string): void {
  const root = contentEl.value
  if (!root) return
  const target = root.querySelector(`[id="${id}"]`) as HTMLElement | null
  if (!target) return
  target.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

watch(
  () => docsIndex.value?.markdown,
  (mdText) => {
    const text = String(mdText || '')
    if (!text.trim()) {
      renderedHtml.value = ''
      toc.value = []
      return
    }

    const rendered = renderMarkdownWithToc(text)
    renderedHtml.value = rendered.html
    toc.value = rendered.toc
  },
  { immediate: true },
)

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

        <div class="min-h-0 flex-1 overflow-hidden">
          <div v-if="loading" class="p-6 text-sm text-slate-600">Loading…</div>
          <div v-else-if="error" class="p-6 text-sm text-red-700">{{ error }}</div>
          <div v-else-if="!docsIndex?.markdown" class="p-6 text-sm text-slate-600">No docs yet. Run indexing for this project.</div>

          <div v-else class="flex min-h-0 h-full overflow-hidden">
            <div ref="contentEl" class="min-w-0 flex-1 overflow-auto p-6">
              <div class="chat-markdown" v-html="renderedHtml" @click="onMarkdownClick"></div>
            </div>

            <aside class="w-72 shrink-0 border-l border-slate-200 bg-white">
              <div class="border-b border-slate-200 px-4 py-3">
                <div class="text-sm font-semibold text-slate-900">On this page</div>
              </div>

              <div class="max-h-full overflow-auto p-4">
                <div v-if="toc.length === 0" class="text-xs text-slate-600">No headings.</div>
                <nav v-else class="flex flex-col gap-2">
                  <a
                    v-for="item in toc"
                    :key="item.id"
                    href="#"
                    class="truncate text-xs text-slate-700 hover:underline"
                    :class="tocIndentClass(item.level)"
                    :title="item.text"
                    @click.prevent="scrollToHeading(item.id)"
                  >
                    {{ item.text }}
                  </a>
                </nav>
              </div>
            </aside>
          </div>
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
