<script setup lang="ts">
import { computed } from 'vue';
import { RouterLink } from 'vue-router';
import type { ProjectInfo } from '../api/openDeepWiki';

const props = defineProps<{
    project: ProjectInfo
    isIndexing: boolean
    isDeleting: boolean
    indexingStep?: string
    indexingDetails?: string
}>()

const emit = defineEmits<{
    (e: 'delete', project: string): void
    (e: 'regenerate', project: string): void
}>()

const p = computed(() => props.project)
</script>

<template>
    <div class="group relative flex flex-col justify-between rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition hover:border-slate-300"
        :class="{ 'opacity-60': isIndexing }">

        <!-- Link Area -->
        <RouterLink v-if="!isIndexing" :to="{ name: 'project', params: { project: p.project } }" class="flex-grow">
            <div class="flex flex-col gap-2 text-center">
                <h3
                    class="text-base font-medium text-slate-900 group-hover:text-[var(--color-primary)] transition-colors">
                    {{ p.project }}
                </h3>

                <div class="text-xs text-slate-600 space-y-1">
                    <div class="truncate px-2" v-if="p.indexed_path" :title="p.indexed_path">
                        {{ p.indexed_path }}
                    </div>
                    <div v-if="p.indexed_at">Indexed: {{ p.indexed_at }}</div>
                    <div v-else class="text-slate-500">Indexed: unknown</div>
                </div>
            </div>
        </RouterLink>

        <!-- Loading State -->
        <div v-else class="flex flex-grow flex-col justify-center gap-3 text-center" aria-disabled="true">
            <div class="text-base font-medium text-slate-900">{{ p.project }}</div>
            <div class="flex items-center justify-center gap-2 text-sm text-slate-600">
                <div class="h-5 w-5 animate-spin rounded-full border-2 border-slate-300 border-t-slate-900" />
                <span>Indexing…</span>
            </div>

            <!-- Detailed Status -->
            <div v-if="indexingStep || indexingDetails"
                class="mx-auto w-full rounded-md border border-slate-200 bg-slate-50 text-left text-xs">
                <div v-if="indexingStep" class="flex items-center justify-between font-medium">
                    <span class="text-slate-900">Status: in_progress</span>
                    <span class="text-slate-600 underline decoration-dotted" :title="indexingStep">({{ indexingStep
                        }})</span>
                </div>
                <p v-if="indexingDetails" class="mt-1 break-all font-mono text-[10px] text-slate-500 line-clamp-2"
                    :title="indexingDetails">
                    {{ indexingDetails }}
                </p>
            </div>

            <div class="text-xs text-slate-600">
                <div class="truncate px-2" v-if="p.indexed_path" :title="p.indexed_path">{{ p.indexed_path }}</div>
                <div class="text-slate-500">Indexed: pending</div>
            </div>
        </div>

        <!-- Actions Footer -->
        <div class="mt-4 flex items-center justify-between border-t border-slate-100 pt-3">
            <button
                class="rounded-md px-3 py-1.5 text-xs font-medium transition-colors hover:bg-[var(--color-primary-light)] text-[var(--color-primary)] disabled:opacity-50"
                :disabled="isDeleting || isIndexing" @click.prevent.stop="emit('regenerate', p.project)"
                title="Regenerate Documentation">
                Regenerate Docs
            </button>

            <button
                class="rounded-md px-3 py-1.5 text-xs font-medium text-red-600 transition-colors hover:bg-red-50 disabled:opacity-50"
                :disabled="isDeleting || isIndexing" @click.prevent.stop="emit('delete', p.project)"
                title="Delete project">
                {{ isDeleting ? 'Deleting…' : 'Delete' }}
            </button>
        </div>
    </div>
</template>
