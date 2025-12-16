import { defineStore } from 'pinia'

import type { QueryResult } from '../api/openDeepWiki'
import {
  ask,
  askStream,
  deleteProjectSession,
  listProjectSessions,
} from '../api/openDeepWiki'

export type ChatRole = 'user' | 'assistant'

export type ChatMessage = {
  role: ChatRole
  content: string
}

export type ChatThread = {
  sessionId?: string
  sessions: string[]
  messages: ChatMessage[]
  loading: boolean
  error?: string
  context?: QueryResult[]
}

type PersistedChatThread = {
  sessionId?: string
  sessions: string[]
  messages: ChatMessage[]
}

type PersistedChatState = Record<string, PersistedChatThread>

const CHAT_STORAGE_KEY = 'open-deepwiki.chat.threads.v1'
let persistTimer: number | undefined

function loadPersistedThreads(): Record<string, ChatThread> {
  try {
    const raw = localStorage.getItem(CHAT_STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw) as PersistedChatState
    if (!parsed || typeof parsed !== 'object') return {}

    const out: Record<string, ChatThread> = {}
    for (const [project, t] of Object.entries(parsed)) {
      if (!project) continue
      if (!t || typeof t !== 'object') continue
      const sessions = Array.isArray((t as any).sessions) ? ((t as any).sessions as string[]) : []
      const messages = Array.isArray((t as any).messages) ? ((t as any).messages as ChatMessage[]) : []
      const sessionId = typeof (t as any).sessionId === 'string' ? ((t as any).sessionId as string) : undefined
      out[project] = {
        sessionId,
        sessions: sessions.filter(Boolean),
        messages: messages.filter((m) => m && (m.role === 'user' || m.role === 'assistant') && typeof m.content === 'string'),
        loading: false,
        error: undefined,
        context: undefined,
      }
    }
    return out
  } catch {
    return {}
  }
}

function toPersistedThreads(threads: Record<string, ChatThread>): PersistedChatState {
  const out: PersistedChatState = {}
  for (const [project, t] of Object.entries(threads)) {
    if (!project || !t) continue
    out[project] = {
      sessionId: t.sessionId,
      sessions: Array.isArray(t.sessions) ? t.sessions : [],
      messages: Array.isArray(t.messages) ? t.messages : [],
    }
  }
  return out
}

function schedulePersist(threads: Record<string, ChatThread>): void {
  if (typeof localStorage === 'undefined') return
  if (persistTimer !== undefined) window.clearTimeout(persistTimer)
  persistTimer = window.setTimeout(() => {
    try {
      localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(toPersistedThreads(threads)))
    } catch {
      // Ignore persistence failures (quota, private mode, etc.).
    }
  }, 200)
}

function ensureThread(threads: Record<string, ChatThread>, project: string): ChatThread {
  if (!threads[project]) {
    threads[project] = { messages: [], loading: false, sessions: [] }
  }
  return threads[project]
}

export const useChatStore = defineStore('chat', {
  state: () => ({
    threads: (typeof window !== 'undefined' ? loadPersistedThreads() : {}) as Record<string, ChatThread>,
  }),
  actions: {
    getThread(project: string): ChatThread {
      return ensureThread(this.threads, project)
    },

    async sendQuestion(project: string, question: string, k = 4): Promise<void> {
      const thread = ensureThread(this.threads, project)
      thread.error = undefined
      thread.loading = true
      thread.context = undefined

      thread.messages.push({ role: 'user', content: question })
      schedulePersist(this.threads)

      try {
        const res = await ask({
          question,
          project,
          k,
          session_id: thread.sessionId,
        })
        thread.sessionId = res.session_id
        if (!thread.sessions.includes(res.session_id)) thread.sessions.unshift(res.session_id)
        thread.messages.push({ role: 'assistant', content: res.answer })
        schedulePersist(this.threads)
      } catch (e) {
        thread.error = e instanceof Error ? e.message : String(e)
      } finally {
        thread.loading = false
        schedulePersist(this.threads)
      }
    },

    async sendQuestionStreamed(project: string, question: string, k = 4): Promise<void> {
      const thread = ensureThread(this.threads, project)
      thread.error = undefined
      thread.loading = true
      thread.context = undefined

      thread.messages.push({ role: 'user', content: question })
      const assistantIndex = thread.messages.push({ role: 'assistant', content: '' }) - 1

      schedulePersist(this.threads)

      const controller = new AbortController()

      try {
        await askStream(
          {
            question,
            project,
            k,
            session_id: thread.sessionId,
          },
          (evt) => {
            if (evt.event === 'meta') {
              thread.sessionId = evt.data.session_id
              if (!thread.sessions.includes(evt.data.session_id)) thread.sessions.unshift(evt.data.session_id)
              schedulePersist(this.threads)
            } else if (evt.event === 'context') {
              thread.context = evt.data.context
            } else if (evt.event === 'token') {
              const m = thread.messages[assistantIndex]
              if (m && m.role === 'assistant') {
                m.content += evt.data.delta
                schedulePersist(this.threads)
              }
            } else if (evt.event === 'done') {
              const m = thread.messages[assistantIndex]
              if (m && m.role === 'assistant') {
                m.content = evt.data.answer
                schedulePersist(this.threads)
              }
            } else if (evt.event === 'error') {
              thread.error = evt.data.message
            }
          },
          { signal: controller.signal },
        )
      } catch (e) {
        thread.error = e instanceof Error ? e.message : String(e)
      } finally {
        thread.loading = false
        controller.abort()
        schedulePersist(this.threads)
      }
    },

    async refreshSessions(project: string): Promise<void> {
      const thread = ensureThread(this.threads, project)
      thread.error = undefined
      try {
        const res = await listProjectSessions(project)
        thread.sessions = res.sessions
        schedulePersist(this.threads)
      } catch (e) {
        thread.error = e instanceof Error ? e.message : String(e)
      }
    },

    selectSession(project: string, sessionId: string): void {
      const thread = ensureThread(this.threads, project)
      thread.sessionId = sessionId
      thread.messages = []
      thread.context = undefined
      thread.error = undefined
      schedulePersist(this.threads)
    },

    newConversation(project: string): void {
      const thread = ensureThread(this.threads, project)
      thread.sessionId = undefined
      thread.messages = []
      thread.context = undefined
      thread.error = undefined
      schedulePersist(this.threads)
    },

    async deleteSession(project: string, sessionId: string): Promise<void> {
      const thread = ensureThread(this.threads, project)
      thread.error = undefined
      try {
        await deleteProjectSession(project, sessionId)
        if (thread.sessionId === sessionId) {
          thread.sessionId = undefined
          thread.messages = []
          thread.context = undefined
        }
        await this.refreshSessions(project)
        schedulePersist(this.threads)
      } catch (e) {
        thread.error = e instanceof Error ? e.message : String(e)
      }
    },
  },
})
