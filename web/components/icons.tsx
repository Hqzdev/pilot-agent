import type { SVGProps } from 'react'

type IconProps = SVGProps<SVGSVGElement>

const stroke = {
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
}

export function CheckMark(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" {...stroke} strokeWidth={2.2} {...props}>
      <path d="m5 12 5 5L20 6" />
    </svg>
  )
}

export function Check(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" {...stroke} strokeWidth={2.2} {...props}>
      <path d="M20 6 9 17l-5-5" />
    </svg>
  )
}

export function CheckBold(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" {...stroke} strokeWidth={2.4} {...props}>
      <path d="M20 6 9 17l-5-5" />
    </svg>
  )
}

export function CheckCopy(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" {...stroke} strokeWidth={2.6} {...props}>
      <path d="M20 6 9 17l-5-5" />
    </svg>
  )
}

export function GitHub(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" {...props}>
      <path d="M12 1.5a10.5 10.5 0 0 0-3.32 20.46c.53.1.72-.23.72-.5v-1.78c-2.92.63-3.54-1.4-3.54-1.4-.48-1.21-1.17-1.54-1.17-1.54-.95-.65.07-.64.07-.64 1.06.07 1.61 1.09 1.61 1.09.94 1.6 2.46 1.14 3.06.87.1-.68.37-1.14.67-1.4-2.33-.27-4.78-1.17-4.78-5.18 0-1.15.41-2.08 1.08-2.82-.11-.27-.47-1.34.1-2.79 0 0 .88-.28 2.88 1.07a9.9 9.9 0 0 1 5.24 0c2-1.35 2.88-1.07 2.88-1.07.57 1.45.21 2.52.1 2.79.67.74 1.08 1.67 1.08 2.82 0 4.02-2.46 4.9-4.8 5.16.38.33.71.97.71 1.96v2.9c0 .28.19.61.73.5A10.5 10.5 0 0 0 12 1.5Z" />
    </svg>
  )
}

export function Download(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" {...stroke} {...props}>
      <path d="M12 3v13" />
      <path d="m7 11 5 5 5-5" />
      <path d="M5 21h14" />
    </svg>
  )
}

export function Rows(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" {...stroke} {...props}>
      <path d="M3 6h18" />
      <path d="M3 12h18" />
      <path d="M3 18h18" />
    </svg>
  )
}

export function Database(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" {...stroke} {...props}>
      <ellipse cx="12" cy="5" rx="8" ry="3" />
      <path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5" />
      <path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" />
    </svg>
  )
}

export function Swap(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" {...stroke} {...props}>
      <path d="m17 2 4 4-4 4" />
      <path d="M3 11v-1a4 4 0 0 1 4-4h14" />
      <path d="m7 22-4-4 4-4" />
      <path d="M21 13v1a4 4 0 0 1-4 4H3" />
    </svg>
  )
}

export function Shield(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" {...stroke} {...props}>
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" />
      <path d="m9 12 2 2 4-4" />
    </svg>
  )
}

export function Refresh(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" {...stroke} {...props}>
      <path d="M21 12a9 9 0 1 1-3-6.7" />
      <path d="M21 4v5h-5" />
    </svg>
  )
}

export function Layers(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" {...stroke} {...props}>
      <path d="M12 2v4" />
      <path d="M12 12l8 4-8 6-8-6 8-4Z" />
    </svg>
  )
}

export function Monitor(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" {...stroke} {...props}>
      <rect x="2" y="4" width="20" height="14" rx="2" />
      <path d="M8 21h8" />
      <path d="M12 18v3" />
    </svg>
  )
}

export function Bolt(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" {...stroke} {...props}>
      <path d="m13 2-3 7h6l-3 7" />
    </svg>
  )
}

export function Code(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" {...stroke} {...props}>
      <path d="M16 18 22 12 16 6" />
      <path d="M8 6 2 12 8 18" />
    </svg>
  )
}

export function Play(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" {...stroke} {...props}>
      <path d="M5 3 19 12 5 21V3Z" />
    </svg>
  )
}

export function CopyIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" {...stroke} {...props}>
      <rect x="9" y="9" width="13" height="13" rx="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  )
}
