const REPO = 'https://github.com/Hqzdev/pilot-agent'

export function Footer() {
  return (
    <>
      <footer className="site">
        <div className="wrap">
          <div className="foot-inner">
            <div className="foot-brand">
              <a className="brand" href="#top">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  className="mark"
                  src="/logo.png"
                  alt="Pilot Agent logo"
                  width={26}
                  height={26}
                />
                Pilot Agent
              </a>
              <p>
                An AI CLI agent that takes you from idea to deployed MVP in one guided terminal
                session.
              </p>
            </div>
            <div className="foot-links">
              <div className="foot-col">
                <h4>Product</h4>
                <a href="#features">Why</a>
                <a href="#install">Install</a>
                <a href="#how">How it works</a>
              </div>
              <div className="foot-col">
                <h4>Resources</h4>
                <a href={REPO} target="_blank" rel="noopener">
                  GitHub repo
                </a>
                <a href={`${REPO}#readme`} target="_blank" rel="noopener">
                  Documentation
                </a>
                <a href={`${REPO}/issues`} target="_blank" rel="noopener">
                  Issues
                </a>
              </div>
            </div>
          </div>
          <div className="foot-bottom">
            <span className="badge">Built for developers who ship</span>
            <span style={{ display: 'inline-flex', gap: 16, alignItems: 'center' }}>
              <a href={REPO} target="_blank" rel="noopener" style={{ color: 'var(--ink-2)' }}>
                GitHub
              </a>
              <span className="badge">MIT License</span>
            </span>
          </div>
        </div>
      </footer>

      <div className="wordmark" aria-hidden="true">
        Pilot
      </div>
    </>
  )
}
