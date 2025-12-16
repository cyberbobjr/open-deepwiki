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

function ensureThread(threads: Record<string, ChatThread>, project: string): ChatThread {
  if (!threads[project]) {
    threads[project] = { messages: [], loading: false, sessions: [] }
  }
  return threads[project]
}

export const useChatStore = defineStore('chat', {
  state: () => ({
    threads: {} as Record<string, ChatThread>,
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
      } catch (e) {
        thread.error = e instanceof Error ? e.message : String(e)
      } finally {
        thread.loading = false
      }
    },

    async sendQuestionStreamed(project: string, question: string, k = 4): Promise<void> {
      const thread = ensureThread(this.threads, project)
      thread.error = undefined
      thread.loading = true
      thread.context = undefined

      thread.messages.push({ role: 'user', content: question })
      const assistantIndex = thread.messages.push({ role: 'assistant', content: '' }) - 1

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
            } else if (evt.event === 'context') {
              thread.context = evt.data.context
            } else if (evt.event === 'token') {
              const m = thread.messages[assistantIndex]
              if (m && m.role === 'assistant') {
                m.content += evt.data.delta
              }
            } else if (evt.event === 'done') {
              const m = thread.messages[assistantIndex]
              if (m && m.role === 'assistant') {
                m.content = evt.data.answer
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
      }
    },

    async refreshSessions(project: string): Promise<void> {
      const thread = ensureThread(this.threads, project)
      thread.error = undefined
      try {
        const res = await listProjectSessions(project)
        thread.sessions = res.sessions
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
    },

    newConversation(project: string): void {
      const thread = ensureThread(this.threads, project)
      thread.sessionId = undefined
      thread.messages = []
      thread.context = undefined
      thread.error = undefined
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
      } catch (e) {
        thread.error = e instanceof Error ? e.message : String(e)
      }
    },
  },
})
