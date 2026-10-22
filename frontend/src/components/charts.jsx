import { useState } from 'react'
import { formatNumber } from '../lib/format.js'

/*
 * Single-series charts only. One mark colour per surface (ink on ivory, lime on
 * charcoal), both checked for >= 3:1 contrast against their surface. Every value is
 * also printed as a direct label, so the hover tooltip enhances but never gates.
 */
const SURFACES = {
  light: { mark: 'bg-ink', muted: 'bg-mist', track: 'bg-cream', text: 'text-ink', sub: 'text-stone', hover: 'bg-cream/70', tip: 'bg-ink text-paper' },
  dark: { mark: 'bg-lime', muted: 'bg-[#7d8268]', track: 'bg-paper/10', text: 'text-paper', sub: 'text-paper/60', hover: 'bg-paper/5', tip: 'bg-lime text-ink' },
}

/**
 * Horizontal bars for a short list of categories (stages, statuses, products).
 * items: [{ key, label, value, muted?, media? }]
 */
export function BarList({ items, surface = 'light', format = formatNumber, unit = '', caption }) {
  const [active, setActive] = useState(null)
  const theme = SURFACES[surface]
  const total = items.reduce((sum, item) => sum + (Number(item.value) || 0), 0)
  const max = Math.max(1, ...items.map((item) => Number(item.value) || 0))

  return (
    <ul className="space-y-1" aria-label={caption}>
      {items.map((item) => {
        const value = Number(item.value) || 0
        const share = total ? Math.round((value / total) * 100) : 0
        const isActive = active === item.key
        return (
          <li
            key={item.key}
            tabIndex={0}
            onMouseEnter={() => setActive(item.key)}
            onMouseLeave={() => setActive(null)}
            onFocus={() => setActive(item.key)}
            onBlur={() => setActive(null)}
            aria-label={`${item.label}: ${format(value)}${unit}, ${share}% of total`}
            className={`relative rounded-xl px-2 py-2 outline-none transition-colors ${isActive ? theme.hover : ''}`}
          >
            <div className="flex items-center gap-3">
              {item.media}
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-3">
                  <span className={`truncate text-sm font-medium ${theme.text}`}>{item.label}</span>
                  <span className={`text-sm font-semibold tabular-nums ${theme.text}`}>{format(value)}{unit}</span>
                </div>
                <div className={`mt-2 h-2 overflow-hidden rounded-full ${theme.track}`}>
                  <div
                    className={`h-full rounded-full transition-[width] duration-700 ease-out ${item.muted ? theme.muted : theme.mark}`}
                    style={{ width: `${Math.max(value ? 3 : 0, (value / max) * 100)}%` }}
                  />
                </div>
              </div>
            </div>
            {isActive && (
              <div role="tooltip" className={`pointer-events-none absolute -top-9 right-2 z-10 rounded-lg px-2.5 py-1.5 text-xs font-semibold shadow-lg ${theme.tip}`}>
                {item.label} · {format(value)}{unit} · {share}%
              </div>
            )}
          </li>
        )
      })}
    </ul>
  )
}

/** A single ratio against 100%. */
export function Meter({ value, label, detail, surface = 'light' }) {
  const theme = SURFACES[surface]
  const percent = Math.max(0, Math.min(100, Number(value) || 0))
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <span className={`text-sm font-medium ${theme.sub}`}>{label}</span>
        <span className={`text-3xl font-semibold tracking-[-0.04em] ${theme.text}`}>{Math.round(percent * 10) / 10}%</span>
      </div>
      <div
        role="meter"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        aria-label={label}
        className={`mt-3 h-3 overflow-hidden rounded-full ${theme.track}`}
      >
        <div className={`h-full rounded-full transition-[width] duration-700 ease-out ${theme.mark}`} style={{ width: `${percent}%` }} />
      </div>
      {detail && <p className={`mt-2 text-xs ${theme.sub}`}>{detail}</p>}
    </div>
  )
}

/** A segmented stage strip: proportional widths with 2px surface gaps and a legend. */
export function StageStrip({ items, surface = 'light' }) {
  const theme = SURFACES[surface]
  const total = items.reduce((sum, item) => sum + (Number(item.value) || 0), 0)
  if (!total) return null
  const shades = surface === 'light'
    ? ['#131410', '#34362d', '#55584c', '#76796a', '#959886', '#acae9b'] // ordinal ramp, validated vs #fbf8f0
    : ['#d4f53c', '#b9d92a', '#9ebc1f', '#839e1a', '#6a7f1a', '#56651c'] // ordinal ramp, validated vs #131410
  return (
    <div>
      <div className="flex h-3 gap-[2px] overflow-hidden rounded-full" role="img" aria-label={items.map((item) => `${item.label} ${item.value}`).join(', ')}>
        {items.filter((item) => Number(item.value) > 0).map((item) => (
          <span key={item.key} title={`${item.label}: ${item.value}`} style={{ flexGrow: Number(item.value), background: shades[items.indexOf(item) % shades.length] }} />
        ))}
      </div>
      <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5">
        {items.map((item, index) => (
          <li key={item.key} className={`flex items-center gap-1.5 text-xs ${theme.sub}`}>
            <span className="size-2 rounded-full" style={{ background: shades[index % shades.length] }} aria-hidden="true" />
            {item.label} <span className={`font-semibold ${theme.text}`}>{item.value}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
