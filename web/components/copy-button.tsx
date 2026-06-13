'use client'

import { useCallback, useRef, useState } from 'react'
import { CopyIcon, CheckCopy } from './icons'

export function CopyButton({ text, label = 'Copy' }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const onCopy = useCallback(async () => {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text)
      } else {
        const ta = document.createElement('textarea')
        ta.value = text
        ta.style.position = 'fixed'
        ta.style.opacity = '0'
        document.body.appendChild(ta)
        ta.focus()
        ta.select()
        document.execCommand('copy')
        document.body.removeChild(ta)
      }
      setCopied(true)
      if (timer.current) clearTimeout(timer.current)
      timer.current = setTimeout(() => setCopied(false), 1800)
    } catch {
      /* no-op */
    }
  }, [text])

  return (
    <button
      type="button"
      className={`copy-btn${copied ? ' copied' : ''}`}
      onClick={onCopy}
      aria-label={copied ? 'Copied' : label}
    >
      <CopyIcon className="ic-copy" />
      <CheckCopy className="ic-check" />
      <span className="lbl">{copied ? 'Copied' : label}</span>
    </button>
  )
}
