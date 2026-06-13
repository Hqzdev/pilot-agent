import type { Metadata } from 'next'
import { Inter, DM_Serif_Display, JetBrains_Mono } from 'next/font/google'
import './globals.css'

const inter = Inter({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-sans',
  display: 'swap',
})

const dmSerif = DM_Serif_Display({
  subsets: ['latin'],
  weight: '400',
  style: ['normal', 'italic'],
  variable: '--font-serif',
  display: 'swap',
})

const jetbrains = JetBrains_Mono({
  subsets: ['latin'],
  weight: ['400', '500', '600'],
  variable: '--font-mono',
  display: 'swap',
})

export const metadata: Metadata = {
  title: 'Pilot Agent — From idea to deployed MVP in one terminal session',
  description:
    'An AI CLI agent that runs your full build pipeline: discovery, planning, coding, acceptance, deploy, and launch copy. Provider-agnostic. Sandboxed. Self-improving.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${dmSerif.variable} ${jetbrains.variable}`}>
      <body>{children}</body>
    </html>
  )
}
