import { Terminal } from '../terminal'
import { Check, Download, GitHub } from '../icons'

const REPO = 'https://github.com/Hqzdev/pilot-agent'

export function Hero() {
  return (
    <section className="hero">
      <div className="wrap">
        <span className="eyebrow">AI CLI Agent · MIT</span>
        <h1>
          From idea to deployed&nbsp;MVP,
          <br />
          in one terminal&nbsp;session.
        </h1>
        <p className="sub">
          An AI CLI agent that runs your full build pipeline:{' '}
          <b>discovery, planning, coding, acceptance, deploy,</b> and launch copy — without
          leaving the terminal.
        </p>
        <div className="hero-cta">
          <a className="btn btn-primary" href="#install">
            <Download />
            Install Now
          </a>
          <a className="btn btn-ghost" href={REPO} target="_blank" rel="noopener">
            <GitHub />
            View on GitHub
          </a>
        </div>
        <div className="hero-meta">
          <span>
            <Check /> Provider-agnostic
          </span>
          <span>
            <Check /> Sandboxed in Docker
          </span>
          <span>
            <Check /> MIT licensed
          </span>
        </div>

        <Terminal />
      </div>
    </section>
  )
}
