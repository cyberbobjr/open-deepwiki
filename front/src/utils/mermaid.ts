import DOMPurify from 'dompurify'

// Lazy-load mermaid to avoid pulling it into the initial bundle until needed.
let mermaidPromise: Promise<any> | null = null
let mermaidInitialized = false
let renderSeq = 0

function stripParenthesizedContent(input: string): string {
  const s = String(input ?? '')
  let out = ''
  let depth = 0

  for (let i = 0; i < s.length; i += 1) {
    const ch = s[i]
    if (ch === '(') {
      depth += 1
      continue
    }
    if (ch === ')') {
      if (depth > 0) depth -= 1
      continue
    }
    if (depth === 0) out += ch
  }

  return out
}

function sanitizeMermaidSource(input: string): string {
  const raw = String(input ?? '').replace(/\r\n/g, '\n').replace(/\r/g, '\n')

  // Aggressive cleanup: remove everything inside parentheses, including nested.
  // Note: Mermaid uses parentheses for some valid syntax (e.g. flowchart node shapes,
  // class diagram method args). This sanitizer trades fidelity for robustness.
  const withoutParens = stripParenthesizedContent(raw)

  const lines = withoutParens.split('\n')
  const cleanedLines: string[] = []
  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed) continue

    // Drop leftover standalone parenthesis tokens.
    if (trimmed === '()' || trimmed === '(' || trimmed === ')') continue

    cleanedLines.push(line.replace(/[\t ]+$/g, ''))
  }

  return cleanedLines.join('\n').trim()
}

async function getMermaid(): Promise<any> {
  if (!mermaidPromise) {
    mermaidPromise = import('mermaid').then((m) => (m as any).default ?? (m as any))
  }
  return mermaidPromise
}

async function ensureMermaidInitialized(): Promise<any> {
  const mermaid = await getMermaid()
  if (!mermaidInitialized) {
    mermaid.initialize({
      startOnLoad: false,
      // Treat diagram text as untrusted input.
      securityLevel: 'strict',
      // Avoid <foreignObject> HTML labels which often get stripped by sanitizers.
      // This keeps labels as plain SVG <text> so they render reliably.
      htmlLabels: false,
      flowchart: {
        htmlLabels: false,
      },
    })
    mermaidInitialized = true
  }
  return mermaid
}

export function installMermaidFence(md: any): void {
  const defaultFence = md.renderer.rules.fence

  md.renderer.rules.fence = (tokens: any[], idx: number, options: any, env: any, self: any) => {
    const token = tokens[idx]
    const infoRaw = String(token?.info ?? '').trim()
    const firstWord = infoRaw.split(/\s+/).filter(Boolean)[0] ?? ''
    const info = firstWord.toLowerCase()

    if (info === 'mermaid') {
      const content = sanitizeMermaidSource(String(token?.content ?? ''))
      const escaped = md.utils.escapeHtml(content)
      return `<div class="mermaid">${escaped}</div>`
    }

    if (typeof defaultFence === 'function') return defaultFence(tokens, idx, options, env, self)
    return self.renderToken(tokens, idx, options)
  }
}

export async function renderMermaidInRoot(root: HTMLElement | null): Promise<void> {
  if (!root) return

  const nodes = Array.from(root.querySelectorAll<HTMLElement>('.mermaid'))
  if (nodes.length === 0) return

  const mermaid = await ensureMermaidInitialized()

  for (const node of nodes) {
    if (node.dataset.mermaidRendered === 'true') continue

    const source = sanitizeMermaidSource(String(node.textContent ?? ''))
    node.dataset.mermaidRendered = 'true'

    if (!source) continue

    try {
      renderSeq += 1
      const id = `mermaid-${Date.now()}-${renderSeq}`

      const result = await mermaid.render(id, source)
      const svgText = typeof result === 'string' ? result : String(result?.svg ?? '')
      if (!svgText) {
        node.textContent = source
        continue
      }

      // Sanitize the SVG before inserting into the DOM.
      const sanitized = DOMPurify.sanitize(svgText, {
        USE_PROFILES: { svg: true, svgFilters: true },
        // Keep return type as string so it can be assigned to innerHTML.
        RETURN_TRUSTED_TYPE: false,
        // Ensure common SVG text tags survive sanitization.
        ADD_TAGS: ['text', 'tspan'],
      } as any)

      node.innerHTML = String(sanitized)
    } catch {
      // Fallback: show the original source as text.
      node.textContent = source
    }
  }
}
