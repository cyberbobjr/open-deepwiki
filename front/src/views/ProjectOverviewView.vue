<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'

import DOMPurify from 'dompurify'
import * as MarkdownIt from 'markdown-it'

import { installMermaidFence, renderMermaidInRoot } from '../utils/mermaid'

import { getProjectDocsIndex, getProjectOverview, type ProjectDocsIndexResponse } from '../api/openDeepWiki'

const route = useRoute()
const router = useRouter()

const project = computed(() => String(route.params.project || '').trim())

const loading = ref(false)
const error = ref<string | undefined>(undefined)
const docsIndex = ref<ProjectDocsIndexResponse | null>(null)

const docLoading = ref(false)
const activeDocError = ref<string | undefined>(undefined)

type TocItem = {
  id: string
  text: string
  level: number
}

const contentEl = ref<HTMLElement | null>(null)
const renderedHtml = ref('')
const toc = ref<TocItem[]>([])

const tocCollapsed = ref(true)

const question = ref('')

watch(
  () => renderedHtml.value,
  () => scheduleMermaidRender(),
)

const MarkdownItCtor: any = (MarkdownIt as any).default ?? (MarkdownIt as any)
const md = new MarkdownItCtor({ linkify: true, breaks: true, html: false })
installMermaidFence(md)

let mermaidTimer: number | undefined

function scheduleMermaidRender(): void {
  if (mermaidTimer) window.clearTimeout(mermaidTimer)
  mermaidTimer = window.setTimeout(async () => {
    await nextTick()
    await renderMermaidInRoot(contentEl.value)
  }, 50)
}

function getApiBase(): string {
  const base = (import.meta.env.VITE_API_BASE as string | undefined) ?? '/api/v1'
  return base.endsWith('/') ? base.slice(0, -1) : base
}

function normalizeDocPath(input: string | undefined): string | undefined {
  const raw = String(input ?? '').trim()
  if (!raw) return
  const p = raw.replace(/^\/+/, '').replace(/^\.\//, '')
  if (!p) return
  if (p === '.' || p === '..') return
  if (p.includes('..')) return
  if (p.includes('\\')) return
  return p
}

const PROJECT_OVERVIEW_DOC = '__project_overview__'

const activeDocPath = computed(() => {
  const raw = String(route.query.doc ?? '').trim()
  if (raw === PROJECT_OVERVIEW_DOC) return PROJECT_OVERVIEW_DOC
  return normalizeDocPath(raw) ?? 'index.md'
})

function isLocalMarkdownHref(href: string): boolean {
  const h = String(href || '').trim()
  if (!h) return false
  if (/^https?:\/\//i.test(h)) return false
  const noQuery = h.split('?')[0] ?? h
  const noHash = (noQuery.split('#')[0] ?? noQuery).trim()
  return noHash.toLowerCase().endsWith('.md')
}

function extractFirstLinkText(inlineToken: any): string {
  const children = (inlineToken?.children ?? []) as any[]
  if (!Array.isArray(children) || children.length === 0) return ''

  let inLink = false
  const parts: string[] = []
  for (const c of children) {
    if (c?.type === 'link_open') {
      inLink = true
      continue
    }
    if (c?.type === 'link_close') {
      if (inLink) break
      continue
    }
    if (!inLink) continue
    if (c?.type === 'text' && typeof c?.content === 'string') {
      parts.push(c.content)
    }
  }

  return parts.join('').trim()
}

function extractFirstLinkHref(inlineToken: any): string {
  const children = (inlineToken?.children ?? []) as any[]
  if (!Array.isArray(children) || children.length === 0) return ''

  for (const c of children) {
    if (c?.type !== 'link_open') continue
    const href = c?.attrGet?.('href')
    if (typeof href === 'string') return href
    const attrs = (c?.attrs ?? []) as Array<[string, string]>
    const found = Array.isArray(attrs) ? attrs.find((a) => a?.[0] === 'href') : undefined
    if (found?.[1]) return String(found[1])
  }

  return ''
}

type FeatureDoc = {
  path: string
  label: string
}

function extractFeatureDocsFromIndex(markdown: string): FeatureDoc[] {
  const text = String(markdown ?? '')
  if (!text.trim()) return []

  const tokens = md.parse(text, {}) as any[]
  const out: FeatureDoc[] = []
  const seen = new Set<string>()

  let inFeatures = false
  let featuresHeadingLevel: number | undefined

  for (let i = 0; i < tokens.length; i += 1) {
    const t = tokens[i]

    if (t?.type === 'heading_open') {
      const tag = String(t?.tag ?? '')
      const level = Number(tag.replace(/[^0-9]/g, '')) || 2
      const inline = tokens[i + 1]
      const title = String(inline?.content ?? '').trim()

      if (title.toLowerCase() === 'features') {
        inFeatures = true
        featuresHeadingLevel = level
        continue
      }

      if (inFeatures && featuresHeadingLevel !== undefined && level <= featuresHeadingLevel) {
        inFeatures = false
        featuresHeadingLevel = undefined
      }

      continue
    }

    if (!inFeatures) continue
    if (t?.type !== 'inline') continue

    const href = extractFirstLinkHref(t)
    if (!href || !isLocalMarkdownHref(href)) continue

    const parts = splitMarkdownHref(href)
    const normalized = normalizeDocPath(parts.url)
    if (!normalized) continue
    if (!normalized.startsWith('features/')) continue

    if (seen.has(normalized)) continue
    seen.add(normalized)

    const label = extractFirstLinkText(t) || normalized
    out.push({ path: normalized, label })
  }

  return out
}

const featureDocs = computed<FeatureDoc[]>(() => extractFeatureDocsFromIndex(docsIndex.value?.markdown ?? ''))

type FeatureOutline = {
  loading: boolean
  error?: string
  headings: TocItem[]
}

const featureOutlineByPath = ref<Record<string, FeatureOutline>>({})

function extractDocHeadingsForSidebar(markdown: string): TocItem[] {
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

    const level = Number(String(h.tagName || '').replace(/[^0-9]/g, '')) || 2
    items.push({ id, text, level })
  }

  // Keep to "heading / subheading" (h2/h3) to avoid duplicating the file title.
  return items.filter((i) => i.level === 2 || i.level === 3)
}

type SidebarHeadingGroup = {
  parent: TocItem
  children: TocItem[]
}

function groupHeadingsForSidebar(headings: TocItem[]): SidebarHeadingGroup[] {
  const groups: SidebarHeadingGroup[] = []
  let current: SidebarHeadingGroup | null = null

  for (const h of headings) {
    if (h.level === 2) {
      current = { parent: h, children: [] }
      groups.push(current)
      continue
    }

    if (h.level === 3) {
      if (!current) continue
      current.children.push(h)
    }
  }

  return groups
}

function isProjectOverviewHref(href: string): boolean {
  const h = String(href || '').trim()
  if (!h) return false
  const noQuery = h.split('?')[0] ?? h
  const noHash = (noQuery.split('#')[0] ?? noQuery).trim()
  return noHash.endsWith('PROJECT_OVERVIEW.md')
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

function docsBaseForProjectAbs(projectName: string): string {
  const base = docsBaseForProject(projectName)
  try {
    const abs = new URL(base, window.location.origin).toString()
    return abs.endsWith('/') ? abs : `${abs}/`
  } catch {
    return base.endsWith('/') ? base : `${base}/`
  }
}

function currentDocUrlAbs(): string {
  const baseAbs = docsBaseForProjectAbs(project.value)
  if (activeDocPath.value === PROJECT_OVERVIEW_DOC) {
    // Use the docs root as the base for resolving relative links.
    return new URL('index.md', baseAbs).toString()
  }

  const doc = normalizeDocPath(activeDocPath.value) ?? 'index.md'
  try {
    return new URL(doc, baseAbs).toString()
  } catch {
    return `${baseAbs}${doc}`
  }
}

function docPathFromResolvedUrl(resolvedUrl: string): string | undefined {
  const resolved = String(resolvedUrl || '').trim()
  if (!resolved) return
  const baseAbs = docsBaseForProjectAbs(project.value)

  let resolvedAbs = resolved
  try {
    resolvedAbs = new URL(resolved, window.location.origin).toString()
  } catch {
    // keep as-is
  }

  if (!resolvedAbs.startsWith(baseAbs)) return
  const rel = resolvedAbs.slice(baseAbs.length)
  return normalizeDocPath(rel)
}

async function navigateToDoc(docPath: string, hash?: string): Promise<void> {
  const p = project.value
  if (!p) return

  const raw = String(docPath || '').trim()
  const doc = raw === PROJECT_OVERVIEW_DOC ? PROJECT_OVERVIEW_DOC : normalizeDocPath(raw)
  if (!doc) return

  await router.push({
    name: 'project',
    params: { project: p },
    query: doc === 'index.md' ? undefined : { doc },
    hash: hash ? `#${String(hash).replace(/^#/, '')}` : undefined,
  })
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

  // In-document anchors scroll within the center panel.
  if (href.startsWith('#')) {
    evt.preventDefault()
    scrollToHeading(href.slice(1))
    return
  }

  // Keep external links from navigating away.
  if (/^https?:\/\//i.test(href) && !isMarkdownDocLink(href)) {
    evt.preventDefault()
    window.open(href, '_blank', 'noopener')
    return
  }

  if (!isMarkdownDocLink(href)) return
  evt.preventDefault()

  if (isProjectOverviewHref(href)) {
    const parts = splitMarkdownHref(href)
    navigateToDoc(PROJECT_OVERVIEW_DOC, parts.hash).catch((e) => {
      error.value = e instanceof Error ? e.message : String(e)
    })
    return
  }

  const parts = splitMarkdownHref(href)
  const baseDir = currentDocUrlAbs().replace(/[^/]+$/, '')
  const resolved = resolveDocsUrl(parts.url, baseDir)

  const docPath = docPathFromResolvedUrl(resolved)
  if (docPath) {
    navigateToDoc(docPath, parts.hash).catch((e) => {
      error.value = e instanceof Error ? e.message : String(e)
    })
    return
  }

  // Fallback (should be rare): load without changing the URL.
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
  () => [docsIndex.value?.markdown, activeDocPath.value, project.value] as const,
  async ([indexMd]) => {
    activeDocError.value = undefined

    const docPath = activeDocPath.value
    const p = project.value
    if (!p) return

    if (docPath === PROJECT_OVERVIEW_DOC) {
      docLoading.value = true
      try {
        const res = await getProjectOverview(p)
        const rendered = renderMarkdownWithToc(String(res.overview ?? ''))
        renderedHtml.value = rendered.html
        toc.value = rendered.toc

        const hash = String(route.hash || '').replace(/^#/, '').trim()
        if (hash) {
          await nextTick()
          scrollToHeading(hash)
        }
      } catch (e) {
        activeDocError.value = e instanceof Error ? e.message : String(e)
        renderedHtml.value = ''
        toc.value = []
      } finally {
        docLoading.value = false
      }
      return
    }

    // index.md comes from the cached docsIndex endpoint.
    if (docPath === 'index.md') {
      const text = String(indexMd || '')
      if (!text.trim()) {
        renderedHtml.value = ''
        toc.value = []
        return
      }

      const rendered = renderMarkdownWithToc(text)
      renderedHtml.value = rendered.html
      toc.value = rendered.toc

      const hash = String(route.hash || '').replace(/^#/, '').trim()
      if (hash) {
        await nextTick()
        scrollToHeading(hash)
      }
      return
    }

    // Other docs are loaded from the docs file endpoint.
    docLoading.value = true
    try {
      const baseAbs = docsBaseForProjectAbs(p)
      const safe = normalizeDocPath(docPath) ?? 'index.md'
      const url = new URL(safe, baseAbs).toString()
      await loadDocFromUrl(url, { hash: String(route.hash || '').replace(/^#/, '').trim() || undefined })
    } catch (e) {
      activeDocError.value = e instanceof Error ? e.message : String(e)
      renderedHtml.value = ''
      toc.value = []
    } finally {
      docLoading.value = false
    }
  },
  { immediate: true },
)

watch(
  () => [project.value, featureDocs.value.map((d) => d.path).join('|')] as const,
  async ([p]) => {
    if (!p) return
    const docs = featureDocs.value
    if (docs.length === 0) {
      featureOutlineByPath.value = {}
      return
    }

    // Reset to only the current feature set.
    const next: Record<string, FeatureOutline> = {}
    for (const d of docs) {
      next[d.path] = { loading: true, headings: [] }
    }
    featureOutlineByPath.value = next

    const baseAbs = docsBaseForProjectAbs(p)
    await Promise.all(
      docs.map(async (d) => {
        try {
          const url = new URL(d.path, baseAbs).toString()
          const res = await fetch(url)
          if (!res.ok) {
            const text = await res.text().catch(() => '')
            throw new Error(text || `Failed to load markdown: ${res.status} ${res.statusText}`)
          }
          const markdown = await res.text()
          const headings = extractDocHeadingsForSidebar(markdown)
          featureOutlineByPath.value = {
            ...featureOutlineByPath.value,
            [d.path]: { loading: false, headings },
          }
        } catch (e) {
          featureOutlineByPath.value = {
            ...featureOutlineByPath.value,
            [d.path]: {
              loading: false,
              headings: [],
              error: e instanceof Error ? e.message : String(e),
            },
          }
        }
      }),
    )
  },
  { immediate: true },
)

watch(
  () => route.hash,
  async (h) => {
    const hash = String(h || '').replace(/^#/, '').trim()
    if (!hash) return
    await nextTick()
    scrollToHeading(hash)
  },
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
          <div class="mt-1 text-xs text-slate-600">Showing: {{ activeDocPath }}</div>
        </div>

        <div class="min-h-0 flex-1 overflow-hidden">
          <div v-if="loading" class="p-6 text-sm text-slate-600">Loading…</div>
          <div v-else-if="error" class="p-6 text-sm text-red-700">{{ error }}</div>
          <div v-else-if="!docsIndex?.markdown" class="p-6 text-sm text-slate-600">No docs yet. Run indexing for this project.</div>

          <div v-else class="flex min-h-0 h-full overflow-hidden">
            <aside class="w-64 shrink-0 border-r border-slate-200 bg-white">
              <div class="border-b border-slate-200 px-4 py-3">
                <div class="text-sm font-semibold text-slate-900">Documents</div>
              </div>

              <div class="max-h-full overflow-auto p-2">
                <nav>
                  <ul class="flex list-none flex-col gap-1">
                    <li>
                      <a
                        href="#"
                        class="block w-full truncate rounded-md px-2 py-1 text-left text-xs text-slate-800 hover:bg-slate-50"
                        :class="activeDocPath === PROJECT_OVERVIEW_DOC ? 'bg-slate-100 font-medium' : ''"
                        title="Project Overview"
                        @click.prevent="navigateToDoc(PROJECT_OVERVIEW_DOC)"
                      >
                        Project Overview
                      </a>
                    </li>

                    <li class="mt-2 px-2 py-1 text-xs font-semibold text-slate-700">Features</li>
                    <li v-if="featureDocs.length === 0" class="px-2 py-1 text-xs text-slate-600">No feature docs found.</li>

                    <li v-for="f in featureDocs" :key="`feature:${f.path}`" class="">
                      <a
                        href="#"
                        class="block w-full truncate rounded-md px-2 py-1 text-left text-xs text-slate-800 hover:bg-slate-50"
                        :class="f.path === activeDocPath ? 'bg-slate-100 font-medium' : ''"
                        :title="f.path"
                        @click.prevent="navigateToDoc(f.path)"
                      >
                        {{ f.label }}
                      </a>

                      <div v-if="featureOutlineByPath[f.path]?.loading" class="px-2 py-1 text-xs text-slate-500">Loading…</div>
                      <div v-else-if="featureOutlineByPath[f.path]?.error" class="px-2 py-1 text-xs text-slate-500">(No headings)</div>

                      <ul v-else class="ml-4 mt-1 flex list-none flex-col gap-1">
                        <li
                          v-for="g in groupHeadingsForSidebar(featureOutlineByPath[f.path]?.headings ?? [])"
                          :key="`${f.path}#${g.parent.id}`"
                        >
                          <a
                            href="#"
                            class="block w-full truncate rounded-md px-2 py-1 text-left text-xs font-medium text-slate-800 hover:bg-slate-50"
                            :title="g.parent.text"
                            @click.prevent="navigateToDoc(f.path, g.parent.id)"
                          >
                            {{ g.parent.text }}
                          </a>

                          <ul class="ml-4 mt-1 flex list-none flex-col gap-1">
                            <li v-for="c in g.children" :key="`${f.path}#${c.id}`">
                              <a
                                href="#"
                                class="block w-full truncate rounded-md px-2 py-1 text-left text-xs text-slate-700 hover:bg-slate-50"
                                :title="c.text"
                                @click.prevent="navigateToDoc(f.path, c.id)"
                              >
                                {{ c.text }}
                              </a>
                            </li>
                          </ul>
                        </li>
                      </ul>
                    </li>
                  </ul>
                </nav>
              </div>
            </aside>

            <div ref="contentEl" class="min-w-0 flex-1 overflow-auto p-6">
              <div v-if="docLoading" class="text-sm text-slate-600">Loading document…</div>
              <div v-else-if="activeDocError" class="text-sm text-red-700">{{ activeDocError }}</div>
              <div v-else class="chat-markdown" v-html="renderedHtml" @click="onMarkdownClick"></div>
            </div>

            <aside
              class="shrink-0 border-l border-slate-200 bg-white"
              :class="tocCollapsed ? 'w-12' : 'w-72'"
            >
              <div class="border-b border-slate-200" :class="tocCollapsed ? 'p-2' : 'px-2 py-2'">
                <div v-if="!tocCollapsed" class="flex items-center justify-between gap-2">
                  <div class="text-sm font-semibold text-slate-900">On this page</div>
                  <button
                    type="button"
                    class="h-8 w-8 rounded-md border border-slate-200 bg-white text-xs text-slate-700"
                    title="Collapse"
                    @click="tocCollapsed = true"
                  >
                    &lt;
                  </button>
                </div>

                <div v-else class="flex items-center justify-center">
                  <button
                    type="button"
                    class="h-8 w-8 rounded-md border border-slate-200 bg-white text-xs text-slate-700"
                    title="Expand"
                    @click="tocCollapsed = false"
                  >
                    &gt;
                  </button>
                </div>
              </div>

              <div v-if="!tocCollapsed" class="max-h-full overflow-auto p-4">
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
