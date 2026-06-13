'use client'

import { useEffect, useState } from 'react'
import { GitHub } from './icons'

const REPO = 'https://github.com/Hqzdev/pilot-agent'

export function Nav() {
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 6)
    window.addEventListener('scroll', onScroll, { passive: true })
    onScroll()
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <header className={`nav${scrolled ? ' scrolled' : ''}`} id="nav">
      <div className="nav-inner">
        <a className="brand" href="#top">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img className="mark" src="/logo.png" alt="Pilot Agent logo" width={26} height={26} />
          Pilot Agent
        </a>
        <nav className="nav-links">
          <a href="#features">Why</a>
          <a href="#install">Install</a>
          <a href="#how">How it works</a>
        </nav>
        <div className="nav-right">
          <a className="btn btn-ghost btn-sm" href={REPO} target="_blank" rel="noopener">
            <GitHub />
            GitHub
          </a>
          <a className="btn btn-primary btn-sm" href="#install">
            Install
          </a>
        </div>
      </div>
    </header>
  )
}
