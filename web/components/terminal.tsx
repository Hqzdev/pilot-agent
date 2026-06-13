'use client'

import { useEffect, useRef } from 'react'

type Line = { html: string; type?: string; after: number }

const LINES: Line[] = [
  { html: '<span class="t-prompt">~/projects/taskflow $</span> ', type: '<span class="t-cmd">pilot-agent run</span>', after: 420 },
  { html: '<span class="t-dim">Loading state from .pilot-agent/STATE.md …</span>', after: 260 },
  { html: '<span class="t-green">✓</span> <span class="t-dim">resumed · context tier 1/3 · 0 open tasks</span>', after: 420 },
  { html: '<span class="phase-tag">DISCOVERY</span> <span class="t-ink">What problem does this MVP solve?</span>', after: 240 },
  { html: '  <span class="t-dim">› a fast task tracker for small teams</span>', after: 200 },
  { html: '<span class="t-green">✓</span> <span class="t-dim">scope captured · 4 questions answered</span>', after: 420 },
  { html: '<span class="phase-tag">PLANNING</span> <span class="t-ink">architecture drafted → 7 milestones</span>', after: 360 },
  { html: '<span class="phase-tag">CODING</span> <span class="t-dim">scaffolding api/ · web/ · db/</span>', after: 220 },
  { html: '  <span class="t-green">+</span> <span class="t-dim">api/routes/tasks.ts</span>', after: 120 },
  { html: '  <span class="t-green">+</span> <span class="t-dim">web/app/board.tsx</span>', after: 220 },
  { html: '<span class="phase-tag">ACCEPTANCE</span> <span class="t-dim">running checks…</span>', after: 320 },
  { html: '<span class="t-green">✓ 12/12 passing</span> <span class="t-dim">— acceptance met</span>', after: 420 },
  { html: '<span class="phase-tag">DEPLOY</span> <span class="t-dim">pushing → building → live</span>', after: 300 },
  { html: '<span class="t-green">✓</span> <span class="t-ink">https://taskflow.app</span> <span class="t-green">is live</span>', after: 360 },
  { html: '<span class="phase-tag">LAUNCH</span> <span class="t-dim">marketing copy generated → LAUNCH.md</span>', after: 500 },
  { html: '<span class="t-green">✓ done</span> <span class="t-dim">idea → deployed MVP in one session</span>', after: 900 },
]

const CURSOR = '<span class="cursor"></span>'
const MAX_LINES = 11

export function Terminal() {
  const termRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const term = termRef.current
    if (!term) return
    const reduce =
      window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduce) return

    const timeouts: ReturnType<typeof setTimeout>[] = []
    let cancelled = false
    const wait = (fn: () => void, ms: number) => {
      const t = setTimeout(() => {
        if (!cancelled) fn()
      }, ms)
      timeouts.push(t)
    }

    let built: string[] = []

    const render = (builtLines: string[], pendingHtml: string | null) => {
      const arr = builtLines.slice(-MAX_LINES + 1)
      let html = arr.map((l) => '<span class="ln">' + l + '</span>').join('')
      if (pendingHtml != null) html += '<span class="ln">' + pendingHtml + CURSOR + '</span>'
      term.innerHTML = html
    }

    const typeCmd = (prefixHtml: string, cmdHtml: string, done: () => void) => {
      const tmp = document.createElement('div')
      tmp.innerHTML = cmdHtml
      const full = tmp.textContent || ''
      const openTag = cmdHtml.slice(0, cmdHtml.indexOf('>') + 1)
      const closeTag = '</span>'
      let i = 0
      const step = () => {
        const partial = prefixHtml + openTag + full.slice(0, i) + closeTag
        render(built, partial)
        i++
        if (i <= full.length) wait(step, 46)
        else {
          built.push(prefixHtml + cmdHtml)
          done()
        }
      }
      step()
    }

    const run = (idx: number) => {
      if (cancelled) return
      if (idx >= LINES.length) {
        render(built, null)
        wait(() => {
          built = []
          term.innerHTML = ''
          run(0)
        }, 3200)
        return
      }
      const line = LINES[idx]
      if (line.type) {
        typeCmd(line.html, line.type, () => {
          render(built, null)
          wait(() => run(idx + 1), line.after)
        })
      } else {
        built.push(line.html)
        render(built, null)
        wait(() => run(idx + 1), line.after)
      }
    }

    term.innerHTML = ''
    wait(() => run(0), 500)

    return () => {
      cancelled = true
      timeouts.forEach(clearTimeout)
    }
  }, [])

  return (
    <div className="terminal">
      <div className="term-bar">
        <div className="term-dots">
          <i />
          <i />
          <i />
        </div>
        <div className="term-title">
          <span className="dot" /> pilot-agent — run
        </div>
      </div>
      {/* Static markup is shown server-side / without JS; the effect animates it. */}
      <div className="term-body" id="term" ref={termRef}>
        <span className="ln">
          <span className="t-prompt">~/projects/taskflow $</span>{' '}
          <span className="t-cmd">pilot-agent run</span>
        </span>
        <span className="ln">
          <span className="t-dim">Loading state from .pilot-agent/STATE.md …</span>
        </span>
        <span className="ln">
          <span className="phase-tag">DISCOVERY</span>{' '}
          <span className="t-ink">What problem does this MVP solve?</span>
        </span>
        <span className="ln">
          <span className="t-green">✓</span>{' '}
          <span className="t-dim">Scope captured · 4 clarifying questions answered</span>
        </span>
        <span className="ln">
          <span className="phase-tag">PLANNING</span>{' '}
          <span className="t-ink">Architecture drafted → 7 milestones</span>
        </span>
        <span className="ln">
          <span className="phase-tag">CODING</span>{' '}
          <span className="t-dim">api/ · web/ · db/ scaffolded</span>
        </span>
        <span className="ln">
          <span className="t-green">✓ acceptance</span>{' '}
          <span className="t-dim">12/12 checks passing</span>
        </span>
        <span className="ln">
          <span className="phase-tag">DEPLOY</span>{' '}
          <span className="t-ink">live → https://taskflow.app</span>{' '}
          <span className="t-green">✓</span>
        </span>
      </div>
    </div>
  )
}
