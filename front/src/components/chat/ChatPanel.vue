<script setup lang="ts">
import DOMPurify from 'dompurify'
import * as MarkdownIt from 'markdown-it'
import { nextTick, onUnmounted, ref, watch } from 'vue'
import { installMermaidFence, renderMermaidInRoot } from '../../utils/mermaid'
import Spinner from '../Spinner.vue'

const props = defineProps<{
    messages: any[] // Using any to be somewhat flexible, but expected to work with Message type
    loading: boolean
    error?: string
    detailsHidden: boolean
    k: number
    question: string
}>()

const emit = defineEmits<{
    (e: 'update:k', value: number): void
    (e: 'update:question', value: string): void
    (e: 'send'): void
    (e: 'link-click', evt: MouseEvent): void
}>()

const messagesEl = ref<HTMLElement | null>(null)

// Local Markdown Setup
const MarkdownItCtor: any = (MarkdownIt as any).default ?? (MarkdownIt as any)
const md = new MarkdownItCtor({ linkify: true, breaks: true, html: false })
installMermaidFence(md)

function renderMarkdown(text: string): string {
    const raw = md.render(text ?? '')
    return DOMPurify.sanitize(raw)
}

function onMarkdownClick(evt: MouseEvent): void {
    emit('link-click', evt)
}

function scrollToBottom(): void {
    nextTick(() => {
        messagesEl.value?.scrollTo({ top: messagesEl.value.scrollHeight, behavior: 'smooth' })
    })
}

// Expose scrollToBottom to parent
defineExpose({ scrollToBottom })

// Mermaid Auto-render
let mermaidTimer: number | undefined

function updateMermaidDiagrams(): void {
    if (mermaidTimer) window.clearTimeout(mermaidTimer)
    mermaidTimer = window.setTimeout(async () => {
        await nextTick()
        if (messagesEl.value) {
            await renderMermaidInRoot(messagesEl.value)
        }
    }, 50)
}

watch(
    () => props.messages,
    () => {
        updateMermaidDiagrams()
    },
    { deep: true, immediate: true }
)

onUnmounted(() => {
    if (mermaidTimer) clearTimeout(mermaidTimer)
})

</script>

<template>
    <section class="flex min-w-0 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white"
        :class="detailsHidden ? 'lg:w-full' : 'lg:w-2/5'">
        <div class="border-b border-slate-200 p-4">
            <div class="text-sm font-semibold text-slate-900">Conversation</div>
        </div>

        <div ref="messagesEl" class="min-h-0 flex-1 overflow-auto p-6">
            <div v-if="messages.length === 0" class="text-sm text-slate-600">Start by asking a question.</div>

            <div v-else class="flex flex-col gap-4">
                <div v-for="(m, idx) in messages" :key="idx" class="flex">
                    <div class="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                        :class="m.role === 'user' ? 'ml-auto bg-slate-50 text-slate-900' : 'mr-auto bg-white text-slate-900'">
                        <div v-if="m.role === 'assistant'" class="chat-markdown">
                            <div v-if="!m.content" class="flex items-center gap-2 text-slate-500 py-1">
                                <Spinner class="h-4 w-4" />
                                <span>Thinking...</span>
                            </div>
                            <div v-else v-html="renderMarkdown(m.content)" @click="onMarkdownClick"></div>
                        </div>
                        <div v-else class="whitespace-pre-wrap">{{ m.content }}</div>
                    </div>
                </div>
            </div>

            <p v-if="error" class="mt-4 text-sm text-red-700">{{ error }}</p>
        </div>

        <!-- Bottom input (pinned) -->
        <form class="shrink-0 border-t border-slate-200 bg-white p-4" @submit.prevent="emit('send')">
            <div class="grid gap-3">
                <div class="flex items-center justify-between gap-3">
                    <label class="flex items-center gap-2 text-sm text-slate-700">
                        <span>K</span>
                        <input :value="k" @input="emit('update:k', Number(($event.target as HTMLInputElement).value))"
                            type="number" min="1" max="50"
                            class="h-9 w-20 rounded-md border border-slate-200 bg-white px-2 text-slate-900"
                            :disabled="loading" />
                    </label>
                </div>

                <div class="flex gap-3">
                    <input :value="question" @input="emit('update:question', ($event.target as HTMLInputElement).value)"
                        class="h-11 flex-1 rounded-md border border-slate-200 bg-white px-3 text-slate-900"
                        placeholder="Ask a follow-up question…" :disabled="loading" />
                    <button type="submit"
                        class="h-11 rounded-md bg-slate-900 px-5 text-sm font-medium text-white disabled:opacity-60"
                        :disabled="loading || !question.trim()">
                        {{ loading ? 'Streaming…' : 'Send' }}
                    </button>
                </div>
            </div>
        </form>
    </section>
</template>
