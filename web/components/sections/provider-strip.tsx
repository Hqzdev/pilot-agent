import { Reveal } from '../reveal'

const PROVIDERS = ['Anthropic', 'OpenAI', 'OpenRouter']

export function ProviderStrip() {
  return (
    <div className="strip">
      <div className="wrap strip-inner">
        <span className="label">bring your own model —</span>
        {PROVIDERS.map((p, i) => (
          <Reveal as="span" key={p} className="badge" delay={i * 0.05}>
            {p}
          </Reveal>
        ))}
      </div>
    </div>
  )
}
