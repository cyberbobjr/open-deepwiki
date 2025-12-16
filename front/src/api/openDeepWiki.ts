export type IndexDirectoryRequest = {
  path: string
  project: string
  reindex?: boolean
}

export type IndexDirectoryResponse = {
  path: string
  project: string
  indexed_methods: number
  indexed_file_summaries?: number
  loaded_method_docs: number
  indexed_at?: string
  status?: 'in_progress' | 'done'
}

export type IndexingStatusResponse = {
  project: string
  status: 'in_progress' | 'done'
  started_at?: string | null
  finished_at?: string | null
  error?: string | null
  total_files?: number | null
  processed_files?: number | null
  remaining_files?: number | null
  current_file?: string | null
}

export type ProjectInfo = {
  project: string
  indexed_path?: string | null
  indexed_at?: string | null
}

export type DeleteProjectRequest = {
  project: string
}

export type DeleteProjectResponse = {
  project: string
  deleted: boolean
  deleted_vectorstore_docs?: boolean
  deleted_graph?: boolean
  deleted_sessions?: number
  deleted_output_dir?: boolean
}

export type AskRequest = {
  question: string
  project: string
  k?: number
  session_id?: string
}

export type QueryResult = {
  id?: string
  signature?: string
  type?: string
  calls?: unknown
  has_javadoc?: boolean
  file_path?: string
  start_line?: number
  end_line?: number
  is_dependency: boolean
  called_from?: string
  page_content: string
}

export type AskResponse = {
  session_id: string
  project: string
  answer: string
  context: QueryResult[]
}

export type AskStreamEvent =
  | { event: 'meta'; data: { session_id: string; project: string } }
  | { event: 'context'; data: { context: QueryResult[] } }
  | { event: 'token'; data: { delta: string } }
  | { event: 'done'; data: { answer: string } }
  | { event: 'error'; data: { message: string } }

function parseSseChunk(buffer: string): { events: AskStreamEvent[]; rest: string } {
  const events: AskStreamEvent[] = []
  const parts = buffer.split('\n\n')
  const complete = parts.slice(0, -1)
  const rest = parts[parts.length - 1] ?? ''

  for (const raw of complete) {
    const lines = raw
      .split('\n')
      .map((l) => l.trimEnd())
      .filter((l) => l.length > 0)

    let eventName = ''
    const dataLines: string[] = []

    for (const line of lines) {
      if (line.startsWith('event:')) {
        eventName = line.slice('event:'.length).trim()
      } else if (line.startsWith('data:')) {
        dataLines.push(line.slice('data:'.length).trim())
      }
    }

    if (!eventName || dataLines.length === 0) continue
    const dataText = dataLines.join('\n')

    try {
      const data = JSON.parse(dataText) as any
      events.push({ event: eventName as any, data } as AskStreamEvent)
    } catch {
      // Ignore malformed events.
    }
  }

  return { events, rest }
}

export async function askStream(
  req: AskRequest,
  onEvent: (evt: AskStreamEvent) => void,
  opts?: { signal?: AbortSignal },
): Promise<void> {
  const url = `${getApiBase()}/ask/stream`
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
    signal: opts?.signal,
  })

  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(text || `Request failed: ${res.status} ${res.statusText}`)
  }

  if (!res.body) {
    throw new Error('Streaming response body is not available.')
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const parsed = parseSseChunk(buffer)
    buffer = parsed.rest

    for (const evt of parsed.events) {
      onEvent(evt)
    }
  }
}

function getApiBase(): string {
  const base = (import.meta.env.VITE_API_BASE as string | undefined) ?? '/api/v1'
  return base.endsWith('/') ? base.slice(0, -1) : base
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${getApiBase()}${path.startsWith('/') ? '' : '/'}${path}`
  const res = await fetch(url, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
  })

  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(text || `Request failed: ${res.status} ${res.statusText}`)
  }

  return (await res.json()) as T
}

export async function listProjects(): Promise<string[]> {
  const url = `${getApiBase()}/projects`
  const res = await fetch(url)
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(text || `Request failed: ${res.status} ${res.statusText}`)
  }
  return (await res.json()) as string[]
}

export async function listProjectsDetails(): Promise<ProjectInfo[]> {
  return requestJson<ProjectInfo[]>('/projects/details', { method: 'GET' })
}

export async function indexDirectory(req: IndexDirectoryRequest): Promise<IndexDirectoryResponse> {
  return requestJson<IndexDirectoryResponse>('/index-directory', {
    method: 'POST',
    body: JSON.stringify(req),
  })
}

export async function getIndexStatus(project: string): Promise<IndexingStatusResponse> {
  const encoded = encodeURIComponent(project)
  return requestJson<IndexingStatusResponse>(`/index-status?project=${encoded}`, { method: 'GET' })
}

export async function ask(req: AskRequest): Promise<AskResponse> {
  return requestJson<AskResponse>('/ask', {
    method: 'POST',
    body: JSON.stringify(req),
  })
}

export type ProjectOverviewRequest = {
  project: string
}

export type ProjectOverviewResponse = {
  project: string
  overview: string
  indexed_path?: string | null
  indexed_at?: string | null
}

export type ProjectDocsIndexResponse = {
  project: string
  markdown: string
  updated_at?: string | null
}

export async function getProjectOverview(project: string): Promise<ProjectOverviewResponse> {
  return requestJson<ProjectOverviewResponse>('/project-overview', {
    method: 'POST',
    body: JSON.stringify({ project } satisfies ProjectOverviewRequest),
  })
}

export async function getProjectDocsIndex(project: string): Promise<ProjectDocsIndexResponse> {
  return requestJson<ProjectDocsIndexResponse>('/project-docs-index', {
    method: 'POST',
    body: JSON.stringify({ project } satisfies ProjectOverviewRequest),
  })
}

export async function deleteProject(project: string): Promise<DeleteProjectResponse> {
  return requestJson<DeleteProjectResponse>('/projects', {
    method: 'DELETE',
    body: JSON.stringify({ project } satisfies DeleteProjectRequest),
  })
}

export type ListSessionsResponse = {
  project: string
  sessions: string[]
}

export type DeleteSessionResponse = {
  project: string
  session_id: string
  deleted: boolean
}

export type ListSessionsRequest = {
  project: string
}

export type DeleteSessionRequest = {
  project: string
  session_id: string
}

export async function listProjectSessions(project: string): Promise<ListSessionsResponse> {
  return requestJson<ListSessionsResponse>('/sessions', {
    method: 'POST',
    body: JSON.stringify({ project } satisfies ListSessionsRequest),
  })
}

export async function deleteProjectSession(
  project: string,
  sessionId: string,
): Promise<DeleteSessionResponse> {
  return requestJson<DeleteSessionResponse>('/sessions/delete', {
    method: 'POST',
    body: JSON.stringify({ project, session_id: sessionId } satisfies DeleteSessionRequest),
  })
}
