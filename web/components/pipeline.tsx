'use client'

import { useEffect, useState, Fragment } from 'react'

const STEPS = ['setup', 'init', 'discovery', 'planning', 'coding', 'acceptance', 'deploy']

export function Pipeline() {
  const [active, setActive] = useState(-1)

  useEffect(() => {
    const reduce =
      window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduce) {
      setActive(STEPS.length - 1)
      return
    }
    const timeouts: ReturnType<typeof setTimeout>[] = []
    let i = 0
    const start = setTimeout(function tick() {
      if (i < STEPS.length) {
        setActive(i)
        i++
        timeouts.push(setTimeout(tick, 500))
      } else {
        setActive(STEPS.length - 1)
      }
    }, 600)
    timeouts.push(start)
    return () => timeouts.forEach(clearTimeout)
  }, [])

  return (
    <div
      className="pipeline"
      role="img"
      aria-label="Pipeline: setup, init, discovery, planning, coding, acceptance, deploy"
    >
      {STEPS.map((step, idx) => (
        <Fragment key={step}>
          <span className={`pipe-step${idx === active ? ' active' : ''}`}>{step}</span>
          {idx < STEPS.length - 1 && <span className="pipe-arrow">→</span>}
        </Fragment>
      ))}
    </div>
  )
}
