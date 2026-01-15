<script setup lang="ts">
import { nextTick, onUnmounted, ref, watch } from 'vue'
import type { QueryResult } from '../../api/openDeepWiki'
import Panel from '../../components/Panel.vue'
import { renderMermaidInRoot } from '../../utils/mermaid'

export type FileContextGroup = {
    filePath: string
    items: QueryResult[]
}

const props = defineProps<{
    detailsHidden: boolean
    fileContextGroups: FileContextGroup[]

    // Doc props
    docOpen: boolean
    docLoading: boolean
    docError?: string
    docTitle?: string
    docUrl?: string
    docRenderedHtml?: string
}>()

const emit = defineEmits<{
    (e: 'close-doc'): void
    (e: 'doc-click', evt: MouseEvent): void
}>()

const docContentEl = ref<HTMLElement | null>(null)
const collapsedFileCards = ref<Record<string, boolean>>({})

function isFileCardCollapsed(filePath: string): boolean {
    return collapsedFileCards.value[String(filePath || '')] === true
}

function toggleFileCard(filePath: string): void {
    const key = String(filePath || '')
    collapsedFileCards.value[key] = !isFileCardCollapsed(key)
}

function fileNameFromPath(pathValue: string): string {
    const p = String(pathValue || '').trim()
    if (!p) return ''
    const parts = p.split('/')
    return parts[parts.length - 1] ?? p
}

// Helper functions for code formatting
function isSourceFilePath(filePath: string): boolean {
    const p = String(filePath || '').trim().toLowerCase()
    if (!p) return false
    const ext = p.includes('.') ? p.split('.').pop() ?? '' : ''
    return [
        'java', 'py', 'ts', 'tsx', 'js', 'jsx', 'go', 'rs', 'c', 'h', 'cpp', 'hpp',
        'cs', 'kt', 'swift', 'scala', 'rb', 'php'
    ].includes(ext)
}

function formatLineNumber(n: number, width: number): string {
    const s = String(n)
    if (s.length >= width) return s
    return `${' '.repeat(width - s.length)}${s}`
}

function withLineNumbers(code: string, startLine: number): string {
    const lines = String(code ?? '').replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n')
    const start = Number.isFinite(startLine) && startLine > 0 ? startLine : 1
    const end = start + Math.max(0, lines.length - 1)
    const width = Math.max(String(start).length, String(end).length)
    return lines.map((line, i) => `${formatLineNumber(start + i, width)} | ${line}`).join('\n')
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

function codeForContext(c: QueryResult): string {
    const code = extractCodeFromPageContent(String(c?.page_content ?? ''))
    const start = Number(c?.start_line)
    const fp = String(c?.file_path ?? '').trim()
    if (fp && isSourceFilePath(fp) && Number.isFinite(start) && start > 0) {
        return withLineNumbers(code, start)
    }
    return code
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

// Mermaid render for docs
const mermaidTimer = ref<number | undefined>(undefined)

function updateDocMermaidDiagrams(): void {
    if (mermaidTimer.value) window.clearTimeout(mermaidTimer.value)
    mermaidTimer.value = window.setTimeout(async () => {
        await nextTick()
        if (docContentEl.value) {
            await renderMermaidInRoot(docContentEl.value)
        }
    }, 50)
}

watch(
    () => props.docRenderedHtml,
    () => updateDocMermaidDiagrams(),
    { immediate: true }
)

onUnmounted(() => {
    if (mermaidTimer.value) clearTimeout(mermaidTimer.value)
})

function scrollToHeading(id: string): void {
    const root = docContentEl.value
    if (!root) return
    const target = root.querySelector(`[id="${id}"]`) as HTMLElement | null
    if (!target) return
    target.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

defineExpose({ scrollToHeading })

</script>

<template>
    <aside v-if="!detailsHidden"
        class="flex min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white">
        <div class="border-b border-slate-200 p-4">
            <div class="text-sm font-semibold text-slate-900">Details</div>
            <div class="mt-1 text-xs text-slate-600">Files retrieved for this conversation.</div>
        </div>

        <div class="min-h-0 flex-1 overflow-auto p-4">
            <div v-if="docOpen" class="mb-4 rounded-lg border border-slate-200 bg-white">
                <div class="flex items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
                    <div class="min-w-0">
                        <div class="truncate text-sm font-semibold text-slate-900" :title="docTitle || 'Document'">
                            {{ docTitle || 'Document' }}
                        </div>
                        <div v-if="docUrl" class="truncate text-xs text-slate-600" :title="docUrl">{{ docUrl }}</div>
                    </div>
                    <button type="button"
                        class="h-8 rounded-md border border-slate-200 bg-white px-2 text-xs text-slate-700"
                        @click="emit('close-doc')">
                        Close
                    </button>
                </div>

                <div ref="docContentEl" class="h-80 overflow-auto p-4">
                    <div v-if="docLoading" class="text-sm text-slate-600">Loading…</div>
                    <div v-else-if="docError" class="text-sm text-red-700">{{ docError }}</div>
                    <div v-else class="chat-markdown" v-html="docRenderedHtml" @click="emit('doc-click', $event)"></div>
                </div>
            </div>

            <div v-if="fileContextGroups.length === 0" class="text-sm text-slate-600">No file references yet.</div>

            <div v-else class="flex flex-col gap-4">
                <Panel v-for="group in fileContextGroups" :key="group.filePath"
                    :title="fileNameFromPath(group.filePath) || group.filePath"
                    :subtitle="group.filePath !== 'snippet' ? group.filePath : undefined" collapsible
                    :collapsed="isFileCardCollapsed(group.filePath)" @toggle="toggleFileCard(group.filePath)">
                    <template #headerRight>
                        <div class="text-xs text-slate-500">{{ group.items.length }} hit(s)</div>
                    </template>

                    <div class="flex flex-col gap-3 p-4">
                        <div v-for="(c, idx) in group.items" :key="idx">
                            <div class="text-xs text-slate-600">{{ contextLocation(c) || 'unknown location' }}</div>
                            <pre
                                class="mt-2 overflow-auto rounded-md bg-slate-50 p-3 text-xs text-slate-900 whitespace-pre">{{
                                    codeForContext(c) }}</pre>
                        </div>
                    </div>
                </Panel>
            </div>
        </div>
    </aside>
</template>
