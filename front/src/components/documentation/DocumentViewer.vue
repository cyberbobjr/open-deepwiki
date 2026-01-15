<script setup lang="ts">
import DOMPurify from 'dompurify';
import MarkdownIt from 'markdown-it';
import { nextTick, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { installMermaidFence, renderMermaidInRoot } from '../../utils/mermaid';

const props = defineProps<{
    markdown: string | null
    activePath: string
    loading: boolean
    error?: string
}>()

const emit = defineEmits<{
    (e: 'navigate', path: string, hash?: string): void
}>()

// --- Markdown Rendering ---
const route = useRoute()
const md = new MarkdownIt({
    html: true,
    linkify: true,
    typographer: true,
})
installMermaidFence(md)

type LocalTocItem = {
    id: string
    text: string
    level: number
}

// Internal state for pre-rendered content and TOC
const renderedHtml = ref('')
const onPageToc = ref<LocalTocItem[]>([])

/**
 * Custom renderer for H2/H3 to add IDs and build local TOC
 */
function renderMarkdownWithToc(raw: string) {
    const tokens = md.parse(raw, {})
    const toc: LocalTocItem[] = []
    const slugCounts: Record<string, number> = {}

    tokens.forEach((token, idx) => {
        if (token.type === 'heading_open') {
            const level = parseInt(token.tag.replace('h', ''), 10)
            if (level === 2 || level === 3) {
                const inlineToken = tokens[idx + 1]
                if (!inlineToken) return

                const text = inlineToken.children
                    ? inlineToken.children.reduce((acc, t) => acc + t.content, '')
                    : inlineToken.content

                let slug = text
                    .toLowerCase()
                    .replace(/[`*_~]/g, '')
                    .replace(/[^a-z0-9\s-]/g, '')
                    .replace(/\s+/g, '-')
                    .replace(/-+/g, '-')
                    .replace(/^-|-$/g, '')

                if (!slug) slug = 'section'

                if (slug in slugCounts) {
                    const current = slugCounts[slug] ?? 0
                    slugCounts[slug] = current + 1
                    slug = `${slug}-${slugCounts[slug]}`
                } else {
                    slugCounts[slug] = 1
                }

                toc.push({ id: slug, text, level })
                token.attrs = [['id', slug]]
            }
        }
    })

    // Use a different rule for tables if needed, but prose usually handles it.
    const html = md.renderer.render(tokens, md.options, {})
    return { html, toc }
}

// Watch markdown changes
watch(() => props.markdown, async (newVal) => {
    if (!newVal) {
        renderedHtml.value = ''
        onPageToc.value = []
        return
    }

    const { html, toc } = renderMarkdownWithToc(newVal)

    // SANITIZE: Critical to allow styles (class) and anchors (id)
    const clean = DOMPurify.sanitize(html, {
        ADD_TAGS: ['mermaid-diagram'],
        ADD_ATTR: ['id', 'class', 'code', 'target']
    })

    renderedHtml.value = clean
    onPageToc.value = toc

    await nextTick()
    await renderMermaidInRoot(document.body)

    if (route.hash) {
        // Wait a bit ensuring DOM is ready (sometimes images/mermaid might shift layout)
        // extending delay slightly or just relying on nextTick
        setTimeout(() => {
            scrollToHeading(route.hash.substring(1))
        }, 100)
    }
})

// Watch hash change
watch(() => route.hash, (newHash) => {
    if (newHash) {
        scrollToHeading(newHash.substring(1))
    }
})

// --- Scroll Handling ---
function scrollToHeading(id: string) {
    const el = document.getElementById(id)
    if (el) {
        el.scrollIntoView({ behavior: 'smooth' })
    }
}

// Intercept clicks on links in the rendered content
function onContentClick(e: MouseEvent) {
    const target = e.target as HTMLElement
    const link = target.closest('a')
    if (!link) return

    const href = link.getAttribute('href')
    if (!href) return

    if (href.startsWith('#')) {
        e.preventDefault()
        scrollToHeading(href.substring(1))
        return
    }

    if (!href.match(/^https?:\/\//)) {
        e.preventDefault()
        emit('navigate', href)
    }
}
</script>

<template>
    <div class="flex flex-1 min-h-0 bg-white">
        <!-- Main Content -->
        <div class="flex-1 overflow-y-auto px-8 py-8" v-if="loading">
            <div class="animate-pulse space-y-4 max-w-3xl mx-auto">
                <div class="h-4 bg-slate-200 rounded w-3/4"></div>
                <div class="h-4 bg-slate-200 rounded"></div>
                <div class="h-4 bg-slate-200 rounded w-5/6"></div>
            </div>
        </div>

        <div class="flex-1 overflow-y-auto px-8 py-8" v-else-if="error">
            <div class="rounded-md bg-red-50 p-4 max-w-3xl mx-auto">
                <div class="text-sm text-red-700">{{ error }}</div>
            </div>
        </div>

        <div class="flex-1 overflow-y-auto px-8 py-8 doc-content scroll-smooth" v-else>
            <div v-if="!markdown" class="text-slate-500 italic text-center mt-10">No content selected.</div>
            <article v-else class="doc-markdown max-w-4xl mx-auto" v-html="renderedHtml" @click="onContentClick">
            </article>
        </div>

        <!-- On-Page TOC (Right Sidebar) -->
        <aside class="hidden w-64 shrink-0 overflow-y-auto border-l border-slate-200 bg-slate-50 p-4 xl:block"
            v-if="onPageToc.length && !loading && !error">
            <div class="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">On this page</div>
            <nav>
                <ul class="flex list-none flex-col gap-1">
                    <li v-for="item in onPageToc" :key="item.id" :class="[item.level === 3 ? 'ml-3' : '']">
                        <a href="#" class="block truncate text-xs text-slate-600 hover:text-slate-900"
                            @click.prevent="scrollToHeading(item.id)">
                            {{ item.text }}
                        </a>
                    </li>
                </ul>
            </nav>
        </aside>
    </div>
</template>

<style>
.mermaid-diagram {
    display: flex;
    justify-content: center;
    overflow-x: auto;
    margin: 1.5rem 0;
    background: transparent;
}
</style>
