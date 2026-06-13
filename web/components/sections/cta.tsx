import { Reveal } from '../reveal'
import { CopyButton } from '../copy-button'
import { GitHub } from '../icons'

const REPO = 'https://github.com/Hqzdev/pilot-agent'
const CURL = 'curl -fsSL https://raw.githubusercontent.com/Hqzdev/pilot-agent/main/install.sh | bash'

export function Cta() {
  return (
    <section className="cta">
      <div className="wrap">
        <Reveal as="div" className="cta-box">
          <h2 className="serif">Ship your next MVP from the terminal</h2>
          <p>One command to install. One session to deploy.</p>
          <div className="cta-cmd">
            <span className="prefix">$</span>
            <code>{CURL}</code>
            <CopyButton text={CURL} />
          </div>
          <div className="cta-actions">
            <a className="btn btn-primary" href="#install">
              Install Now
            </a>
            <a className="btn btn-ghost" href={REPO} target="_blank" rel="noopener">
              <GitHub />
              View on GitHub
            </a>
          </div>
        </Reveal>
      </div>
    </section>
  )
}
