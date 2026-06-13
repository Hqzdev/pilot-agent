import { Reveal } from '../reveal'
import {
  CheckBold,
  Rows,
  Database,
  Swap,
  Shield,
  Refresh,
  Layers,
} from '../icons'

const ROWS = [
  { icon: Rows, label: 'Full pipeline in one command' },
  { icon: Database, label: 'State persisted across sessions' },
  { icon: Swap, label: 'Switch AI provider mid-session' },
  { icon: Shield, label: 'Docker-sandboxed execution' },
  { icon: Refresh, label: 'Verification loop until acceptance passes' },
  { icon: Layers, label: 'Self-improving via inspectable lessons' },
]

export function Comparison() {
  return (
    <section id="features">
      <div className="wrap">
        <Reveal as="div" className="sec-head">
          <span className="eyebrow">Why Pilot Agent</span>
          <h2 className="serif">A sandboxed operator, not a chat window</h2>
          <p>
            It plans, writes, verifies and deploys — then explains what it learned. Here&apos;s
            what that replaces.
          </p>
        </Reveal>
        <Reveal as="table" className="cmp">
          <thead>
            <tr>
              <th>Capability</th>
              <th className="col-mark">Pilot Agent</th>
              <th className="col-mark muted">Manual workflow</th>
            </tr>
          </thead>
          <tbody>
            {ROWS.map(({ icon: Icon, label }) => (
              <tr key={label}>
                <td className="feat">
                  <Icon /> {label}
                </td>
                <td className="mark">
                  <span className="yes">
                    <CheckBold />
                  </span>
                </td>
                <td className="mark">
                  <span className="no">—</span>
                </td>
              </tr>
            ))}
          </tbody>
        </Reveal>
      </div>
    </section>
  )
}
