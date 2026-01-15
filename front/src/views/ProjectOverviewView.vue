<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  getProjectDocsToc,
  type ProjectDocsTocResponse,
  readProjectDoc
} from '../api/openDeepWiki'
// Child components
import DocumentViewer from '../components/documentation/DocumentViewer.vue'
import ProjectSidebar from '../components/documentation/ProjectSidebar.vue'

const route = useRoute()
const router = useRouter()

const project = ref('')
const activeDocPath = ref('')

const loadingToc = ref(false)
const error = ref<string | undefined>(undefined)
const docsToc = ref<ProjectDocsTocResponse | null>(null)

const docLoading = ref(false)
const activeDocError = ref<string | undefined>(undefined)
const activeDocContent = ref<string | null>(null)

function normalizeProject(p: string | string[]): string {
  if (Array.isArray(p)) return p[0] || ''
  return p
}

onMounted(() => {
  if (route.params.project) {
    project.value = normalizeProject(route.params.project as string | string[])
  }
  // Initialize path from query
  const qPath = route.query.path as string
  activeDocPath.value = qPath || 'PROJECT_OVERVIEW.md'

  if (project.value) {
    loadToc()
    loadContent()
  }
})

watch(() => route.params.project, (newP) => {
  if (newP) {
    project.value = normalizeProject(newP as string | string[])
    loadToc()
  }
})

watch(() => route.query.path, (newPath) => {
  const p = (newPath as string) || 'PROJECT_OVERVIEW.md'
  if (p !== activeDocPath.value) {
    activeDocPath.value = p
    loadContent()
  }
})


async function loadToc() {
  const p = project.value
  if (!p) return

  loadingToc.value = true
  error.value = undefined

  try {
    const res = await getProjectDocsToc(p)
    docsToc.value = res
  } catch (e) {
    console.error("Failed to load TOC", e)
    error.value = "Failed to load documentation structure. Is the project indexed?"
    docsToc.value = null
  } finally {
    loadingToc.value = false
  }
}

async function loadContent() {
  const p = project.value
  const path = activeDocPath.value
  if (!p || !path) return

  docLoading.value = true
  activeDocError.value = undefined
  activeDocContent.value = null

  try {
    const content = await readProjectDoc(p, path)
    activeDocContent.value = content
  } catch (e) {
    console.error(e)
    activeDocError.value = `Failed to load document: ${path}. It might not exist or the server is down.`
  } finally {
    docLoading.value = false
  }
}


// Navigation Handler
function onNavigate(docPath: string, hash?: string) {
  console.log(docPath, hash)
  // Update route query
  router.push({
    query: { ...route.query, path: docPath },
    hash: hash ? `#${hash}` : undefined
  })
}

</script>

<template>
  <div class="flex h-screen w-full flex-col bg-slate-50">
    <!-- Header -->
    <header class="flex h-14 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-4">
      <div class="flex items-center gap-2">
        <h1 class="text-lg font-semibold text-slate-800">{{ project }} Documentation</h1>
        <span v-if="loadingToc" class="text-xs text-slate-400 ml-2">Loading TOC...</span>
      </div>
      <div class="text-xs text-slate-500" v-if="docsToc?.updated_at">
        Last Updated: {{ new Date(docsToc.updated_at).toLocaleString() }}
      </div>
    </header>

    <div class="flex min-h-0 flex-1 overflow-hidden">
      <!-- Left Sidebar (TOC) -->
      <ProjectSidebar class="hidden md:flex" :toc="docsToc?.toc" :active-path="activeDocPath" @navigate="onNavigate" />

      <!-- Main Content Area -->
      <main class="flex flex-1 flex-col overflow-hidden bg-white relative">
        <div v-if="!docsToc && !loadingToc && error" class="p-8 text-red-600">
          {{ error }}
        </div>
        <DocumentViewer v-else :markdown="activeDocContent" :active-path="activeDocPath" :loading="docLoading"
          :error="activeDocError" @navigate="onNavigate" />
      </main>
    </div>
  </div>
</template>
