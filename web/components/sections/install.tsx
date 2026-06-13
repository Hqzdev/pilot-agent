import { Reveal } from '../reveal'
import { CopyButton } from '../copy-button'
import { Monitor, Bolt, Code, Play } from '../icons'

const INSTALL_URL = 'https://pilotagent.vercel.app/install.sh'
const CURL = `curl -fsSL ${INSTALL_URL} | bash`
const CURL_SKIP =
  `curl -fsSL ${INSTALL_URL} | bash -s -- --skip-setup`
const UV = 'uv tool install git+https://github.com/Hqzdev/pilot-agent'
const QUICKSTART = `pilot-agent setup
cd your-project
pilot-agent init
pilot-agent run`

export function Install() {
  return (
    <section id="install">
      <div className="wrap">
        <Reveal as="div" className="sec-head">
          <span className="eyebrow">Get started</span>
          <h2 className="serif">Get started in 30 seconds</h2>
          <p>One command and you&apos;re in. Pick the install path that matches your setup.</p>
        </Reveal>

        <div className="install-wrapper">
          <div className="install-inner">
            <div className="install-list">
              <Reveal className="install-box">
                <div className="ib-head">
                  <span className="ib-label">
                    <Monitor /> Linux / macOS / WSL2 — recommended
                  </span>
                  <CopyButton text={CURL} />
                </div>
                <div className="code-row">
                  <pre>
                    <span className="c-cmd">curl</span> <span className="c-flag">-fsSL</span>{' '}
                    <span className="c-str">
                      {INSTALL_URL}
                    </span>{' '}
                    | <span className="c-cmd">bash</span>
                  </pre>
                </div>
              </Reveal>

              <Reveal className="install-box" delay={0.05}>
                <div className="ib-head">
                  <span className="ib-label">
                    <Bolt /> Skip the setup wizard
                  </span>
                  <CopyButton text={CURL_SKIP} />
                </div>
                <div className="code-row">
                  <pre>
                    <span className="c-cmd">curl</span> <span className="c-flag">-fsSL</span>{' '}
                    <span className="c-str">
                      {INSTALL_URL}
                    </span>{' '}
                    | <span className="c-cmd">bash</span>{' '}
                    <span className="c-flag">-s -- --skip-setup</span>
                  </pre>
                </div>
              </Reveal>

              <Reveal className="install-box" delay={0.1}>
                <div className="ib-head">
                  <span className="ib-label">
                    <Code /> Manual install with uv
                  </span>
                  <CopyButton text={UV} />
                </div>
                <div className="code-row">
                  <pre>
                    <span className="c-cmd">uv</span> tool install{' '}
                    <span className="c-str">git+https://github.com/Hqzdev/pilot-agent</span>
                  </pre>
                </div>
              </Reveal>
            </div>

            <div className="quickstart">
              <div className="qs-label">
                <Play /> Then — your first build
              </div>
              <Reveal className="install-box">
                <div className="ib-head">
                  <span className="ib-label">four commands</span>
                  <CopyButton text={QUICKSTART} />
                </div>
                <div className="code-row">
                  <pre>
                    <span className="c-cmd">pilot-agent</span> setup{'     '}
                    <span className="c-cmt"># configure AI provider and API key</span>
                    {'\n'}
                    <span className="c-cmd">cd</span> <span className="c-path">your-project</span>
                    {'\n'}
                    <span className="c-cmd">pilot-agent</span> init{'      '}
                    <span className="c-cmt"># create .pilot-agent/STATE.md</span>
                    {'\n'}
                    <span className="c-cmd">pilot-agent</span> run{'       '}
                    <span className="c-cmt"># start the build pipeline</span>
                  </pre>
                </div>
              </Reveal>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
