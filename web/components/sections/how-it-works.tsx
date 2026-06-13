import { Reveal } from '../reveal'
import { Pipeline } from '../pipeline'

export function HowItWorks() {
  return (
    <section id="how">
      <div className="wrap">
        <Reveal as="div" className="sec-head">
          <span className="eyebrow">The pipeline</span>
          <h2 className="serif">How it works</h2>
          <p>Six phases, one continuous session. You stay in control at every checkpoint.</p>
        </Reveal>

        <Reveal>
          <Pipeline />
        </Reveal>

        <Reveal as="ol" className="steps">
          <li>
            <h3>
              <code>pilot-agent setup</code> Configure your provider
            </h3>
            <p>
              Choose your AI provider — Anthropic, OpenAI or OpenRouter — and add your API key.
              One-time setup.
            </p>
          </li>
          <li>
            <h3>
              <code>pilot-agent init</code> Initialize project state
            </h3>
            <p>
              Creates <code className="inline">.pilot-agent/STATE.md</code> so the agent has a
              durable memory of your project from line one.
            </p>
          </li>
          <li>
            <h3>
              <code>pilot-agent run</code> Discovery phase
            </h3>
            <p>
              The agent enters discovery and asks clarifying questions until the scope of your MVP
              is unambiguous.
            </p>
          </li>
          <li>
            <h3>Plan · code · test — automatically</h3>
            <p>
              It drafts the plan, writes the code and runs the tests on its own. You review and
              approve at each phase boundary.
            </p>
          </li>
          <li>
            <h3>Deploy &amp; launch copy</h3>
            <p>
              The same <code className="inline">run</code> continues through deployment, then
              generates ready-to-use launch and marketing copy.
            </p>
          </li>
          <li>
            <h3>Done — your MVP is live</h3>
            <p>
              A deployed product, a clean state file, and a record of every decision the agent made
              along the way.
            </p>
          </li>
        </Reveal>
      </div>
    </section>
  )
}
