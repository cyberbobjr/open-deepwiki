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
                    <li>
                        <a href="#"
                            class="block w-full truncate rounded-md px-2 py-1 text-left text-xs text-slate-800 hover:bg-slate-50"
                            :class="activePath === 'PROJECT_OVERVIEW.md' || activePath === '__project_overview__' ? 'bg-slate-100 font-medium' : ''"
                            title="Project Overview" @click.prevent="onNav('PROJECT_OVERVIEW.md')">
                            Project Overview
                        </a>
                    </li>

                    <!-- Categories/Modules -->
                    <template v-if="toc?.categories">
                        <template v-for="(modules, category) in toc.categories" :key="category">
                            <li class="mt-2 px-2 py-1 text-xs font-semibold text-slate-700 capitalize">{{ category }}
                            </li>
                            <li v-for="m in modules" :key="`module:${m.path}`" class="">
                                <a href="#"
                                    class="block w-full truncate rounded-md px-2 py-1 text-left text-xs text-slate-800 hover:bg-slate-50"
                                    :class="m.path === activePath ? 'bg-slate-100 font-medium' : ''" :title="m.path"
                                    @click.prevent="onNav(m.path)">
                                    {{ m.short_title || m.title }}
                                </a>

                                <!-- Sub-headings inside module -->
                                <ul v-if="m.headings?.length && m.path === activePath"
                                    class="ml-4 mt-1 flex list-none flex-col gap-1">
                                    <li v-for="g in groupHeadingsForSidebar(m.headings)"
                                        :key="`${m.path}#${g.parent.id}`">
                                        <a href="#"
                                            class="block w-full truncate rounded-md px-2 py-1 text-left text-xs font-medium text-slate-800 hover:bg-slate-50"
                                            :title="g.parent.text" @click.prevent="onNav(m.path, g.parent.id)">
                                            {{ g.parent.text }}
                                        </a>
                                        <ul class="ml-4 mt-1 flex list-none flex-col gap-1">
                                            <li v-for="c in g.children" :key="`${m.path}#${c.id}`">
                                                <a href="#"
                                                    class="block w-full truncate rounded-md px-2 py-1 text-left text-xs text-slate-700 hover:bg-slate-50"
                                                    :title="c.text" @click.prevent="onNav(m.path, c.id)">
                                                    {{ c.text }}
                                                </a>
                                            </li>
                                        </ul>
                                    </li>
                                </ul>
                            </li>
                        </template>
                    </template>

                    <!-- Fallback: Modules flat list -->
                    <template v-else-if="(toc as any)?.modules?.length">
                        <li class="mt-2 px-2 py-1 text-xs font-semibold text-slate-700">Modules (Uncategorized)</li>
                        <li v-for="m in (toc as any).modules" :key="`module:${m.path}`" class="">
                            <a href="#" :class="m.path === activePath ? 'bg-slate-100 font-medium' : ''"
                                @click.prevent="onNav(m.path)">{{ m.title }}</a>
                        </li>
                    </template>


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

                        <!-- Sub-headings inside feature -->
                        <ul v-if="f.headings?.length && f.path === activePath"
                            class="ml-4 mt-1 flex list-none flex-col gap-1">
                            <li v-for="g in groupHeadingsForSidebar(f.headings)" :key="`${f.path}#${g.parent.id}`">
                                <a href="#"
                                    class="block w-full truncate rounded-md px-2 py-1 text-left text-xs font-medium text-slate-800 hover:bg-slate-50"
                                    :title="g.parent.text" @click.prevent="onNav(f.path, g.parent.id)">
                                    {{ g.parent.text }}
                                </a>
                            </li>
                        </ul>
                    </li>
                </ul>
            </nav>
        </div>
    </aside>
</template>
