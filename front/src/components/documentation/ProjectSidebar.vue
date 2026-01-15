<script setup lang="ts">
import { type ProjectDocsTocResponse, type TocHeading } from '../../api/openDeepWiki';

const props = defineProps<{
    toc: ProjectDocsTocResponse['toc'] | null | undefined
    activePath: string
}>()

const emit = defineEmits<{
    (e: 'navigate', path: string, hash?: string): void
}>()

type TocItem = {
    id: string
    text: string
    level: number
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


function processTocHeadings(rawHeadings: TocHeading[]): TocItem[] {
    const seen: Record<string, number> = {}
    return rawHeadings.map(h => {
        const base = slugifyHeading(h.text)
        const n = (seen[base] ?? 0) + 1
        seen[base] = n
        const id = n === 1 ? base : `${base}-${n}`
        return { id, text: h.text, level: h.level }
    }).filter(h => h.level === 2 || h.level === 3)
}

type SidebarHeadingGroup = {
    parent: TocItem
    children: TocItem[]
}

function groupHeadingsForSidebar(headings: TocHeading[]): SidebarHeadingGroup[] {
    const processed = processTocHeadings(headings)
    const groups: SidebarHeadingGroup[] = []
    let current: SidebarHeadingGroup | null = null

    for (const h of processed) {
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

function onNav(path: string, hash?: string) {
    emit('navigate', path, hash)
}
</script>

<template>
    <aside class="flex w-64 flex-col border-r border-slate-200 bg-white">
        <!-- Removed header "Documents" as requested -->

        <div class="flex-1 overflow-y-auto py-2">
            <nav>
                <ul class="flex list-none flex-col gap-1">
                    <!-- Overview -->
                    <li class="px-2 py-1 text-xs font-semibold text-slate-700">Overview</li>
                    <li v-if="toc?.overview">
                        <a href="#"
                            class="block w-full truncate rounded-md px-2 py-1 text-left text-xs text-slate-800 hover:bg-slate-50"
                            :class="activePath === toc.overview.path || activePath === '__project_overview__' ? 'bg-slate-100 font-medium' : ''"
                            :title="toc.overview.title" @click.prevent="onNav(toc.overview.path)">
                            {{ toc.overview.short_title || toc.overview.title }}
                        </a>
                        <!-- Sub-headings inside overview -->
                        <ul v-if="toc.overview.headings?.length && toc.overview.path === activePath"
                            class="ml-4 mt-1 flex list-none flex-col gap-1">
                            <li v-for="g in groupHeadingsForSidebar(toc.overview.headings)"
                                :key="`${toc.overview.path}#${g.parent.id}`">
                                <a href="#"
                                    class="block w-full truncate rounded-md px-2 py-1 text-left text-xs font-medium text-slate-800 hover:bg-slate-50"
                                    :title="g.parent.text" @click.prevent="onNav(toc.overview.path, g.parent.id)">
                                    {{ g.parent.text }}
                                </a>
                                <ul class="ml-4 mt-1 flex list-none flex-col gap-1">
                                    <li v-for="c in g.children" :key="`${toc.overview.path}#${c.id}`">
                                        <a href="#"
                                            class="block w-full truncate rounded-md px-2 py-1 text-left text-xs text-slate-700 hover:bg-slate-50"
                                            :title="c.text" @click.prevent="onNav(toc.overview.path, c.id)">
                                            {{ c.text }}
                                        </a>
                                    </li>
                                </ul>
                            </li>
                        </ul>
                    </li>

                    <!-- Features -->
                    <li class="mt-2 px-2 py-1 text-xs font-semibold text-slate-700">Features</li>
                    <li v-if="!toc?.features?.length" class="px-2 py-1 text-xs text-slate-600">No feature docs found.
                    </li>

                    <li v-for="f in toc?.features ?? []" :key="`feature:${f.path}`" class="">
                        <a href="#"
                            class="block w-full truncate rounded-md px-2 py-1 text-left text-xs text-slate-800 hover:bg-slate-50"
                            :class="f.path === activePath ? 'bg-slate-100 font-medium' : ''" :title="f.path"
                            @click.prevent="onNav(f.path)">
                            {{ f.short_title || f.title }}
                        </a>

                        <!-- Feature Details (Active only) -->
                        <div v-if="f.path === activePath || f.sub_chapters?.some(s => s.path === activePath) || f.implementation_details?.some(i => i.path === activePath)"
                            class="ml-2 border-l border-slate-200 pl-2">

                            <!-- Sub-chapters (Deep Dives) -->
                            <ul v-if="f.sub_chapters?.length" class="mt-1 flex list-none flex-col gap-1">
                                <li v-for="sub in f.sub_chapters" :key="sub.path">
                                    <a href="#"
                                        class="block w-full truncate rounded-md px-2 py-0.5 text-left text-[11px] text-slate-600 hover:bg-slate-50"
                                        :class="sub.path === activePath ? 'text-indigo-600 font-medium bg-indigo-50' : ''"
                                        :title="sub.title" @click.prevent="onNav(sub.path)">
                                        {{ sub.short_title || sub.title }}
                                    </a>
                                </li>
                            </ul>

                            <!-- Implementation Details (Modules) -->
                            <div v-if="f.implementation_details?.length" class="mt-2">
                                <span
                                    class="block px-2 text-[10px] font-semibold uppercase text-slate-400">Implementation
                                    Details</span>
                                <ul class="mt-0.5 flex list-none flex-col gap-0.5">
                                    <li v-for="impl in f.implementation_details" :key="impl.path">
                                        <a href="#"
                                            class="block w-full truncate rounded-md px-2 py-0.5 text-left text-[11px] text-slate-600 hover:bg-slate-50"
                                            :class="impl.path === activePath ? 'text-indigo-600 font-medium bg-indigo-50' : ''"
                                            :title="impl.title" @click.prevent="onNav(impl.path)">
                                            {{ impl.short_title || impl.title }}
                                        </a>
                                    </li>
                                </ul>
                            </div>

                            <!-- In-page Headings (for the active doc) -->
                            <template v-if="f.path === activePath && f.headings?.length">
                                <div class="mt-2 text-[10px] font-semibold text-slate-400 px-2 uppercase">On this page
                                </div>
                                <ul class="mt-0.5 flex list-none flex-col gap-0.5">
                                    <li v-for="g in groupHeadingsForSidebar(f.headings)"
                                        :key="`${f.path}#${g.parent.id}`">
                                        <a href="#"
                                            class="block w-full truncate rounded-md px-2 py-0.5 text-left text-[11px] text-slate-500 hover:text-slate-800"
                                            :title="g.parent.text" @click.prevent="onNav(f.path, g.parent.id)">
                                            {{ g.parent.text }}
                                        </a>
                                    </li>
                                </ul>
                            </template>
                        </div>
                    </li>
                </ul>
            </nav>
        </div>
    </aside>
</template>
