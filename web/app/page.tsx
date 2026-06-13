import { Nav } from '@/components/nav'
import { Hero } from '@/components/sections/hero'
import { ProviderStrip } from '@/components/sections/provider-strip'
import { Comparison } from '@/components/sections/comparison'
import { Install } from '@/components/sections/install'
import { HowItWorks } from '@/components/sections/how-it-works'
import { Cta } from '@/components/sections/cta'
import { Footer } from '@/components/sections/footer'

export default function Home() {
  return (
    <>
      <Nav />
      <a id="top" />
      <Hero />
      <ProviderStrip />
      <Comparison />
      <hr className="divider" />
      <Install />
      <hr className="divider" />
      <HowItWorks />
      <Cta />
      <Footer />
    </>
  )
}
