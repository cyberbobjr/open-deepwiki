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
import IconChat from '../components/ui/IconChat.vue'
import IconSend from '../components/ui/IconSend.vue'

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

// Chat integration
const chatInput = ref('')

function goToChat() {
  const q = chatInput.value.trim()
  if (!q) return

  router.push({
    name: 'chat',
    params: { project: project.value },
    query: { q }
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

    <div class="flex min-h-0 flex-1 overflow-hidden pb-20">
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

    <!-- Floating Chat Bar -->
    <div class="fixed bottom-6 left-0 right-0 z-50 flex justify-center px-4 pointer-events-none">
      <div
        class="pointer-events-auto flex w-full max-w-2xl items-center gap-2 rounded-2xl border border-slate-200 bg-white/90 p-2 shadow-xl backdrop-blur-sm transition-all hover:bg-white focus-within:bg-white focus-within:ring-2 focus-within:ring-slate-900/5">
        <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-500">
          <IconChat />
        </div>
        <input v-model="chatInput" @keydown.enter="goToChat" type="text"
          placeholder="Ask a question about this documentation..."
          class="flex-1 bg-transparent px-2 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none" />
        <button @click="goToChat" :disabled="!chatInput.trim()"
          class="flex h-10 items-center gap-2 rounded-xl bg-slate-900 px-4 text-sm font-medium text-white transition-colors hover:bg-slate-800 disabled:opacity-50 disabled:cursor-not-allowed">
          <span>Ask</span>
          <IconSend />
        </button>
      </div>
    </div>
  </div>
</template>
