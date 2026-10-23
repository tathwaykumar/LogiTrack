import { useEffect } from 'react'
import { formatLabel } from '../lib/format.js'

const ICON_PATHS = {
  grid: 'M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z',
  box: 'm4 7.5 8-4.5 8 4.5v9L12 21l-8-4.5zM4 7.5l8 4.5 8-4.5M12 12v9',
  route: 'M6 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM18 9a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM6 15V9a3 3 0 0 1 3-3h7M18 9v6a3 3 0 0 1-3 3H8',
  pin: 'M12 21s6.5-5.4 6.5-11.2a6.5 6.5 0 1 0-13 0C5.5 15.6 12 21 12 21ZM12 12.3a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z',
  truck: 'M2.5 6.5h11v10h-11zM13.5 9.5h4l3.5 3.5v3.5h-7.5M6.5 19.5a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM17.5 19.5a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z',
  vehicle: 'M5 16.5h14M4 16.5l1.6-5.2A2 2 0 0 1 7.5 10h9a2 2 0 0 1 1.9 1.3L20 16.5v2.5H4zM7.5 19v1.5M16.5 19v1.5M7 14h1M16 14h1',
  users: 'M16 20v-1.5a4 4 0 0 0-4-4H6.5a4 4 0 0 0-4 4V20M9.2 11a3.7 3.7 0 1 0 0-7.4 3.7 3.7 0 0 0 0 7.4ZM21.5 20v-1.5a4 4 0 0 0-3-3.9M15.5 3.7a3.7 3.7 0 0 1 0 7.2',
  user: 'M19 20v-1.5a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4V20M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z',
  card: 'M3 6.5h18v11H3zM3 10h18M7 14.5h4',
  file: 'M6 3h8l4.5 4.5V21H6zM14 3v4.5h4.5M9 13h6M9 17h4',
  chart: 'M4 20V11M10 20V5M16 20v-6M21 20H3',
  shop: 'M4 9.5h16l-1.2 10.5H5.2zM8.5 9.5V7.5a3.5 3.5 0 0 1 7 0v2',
  search: 'M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14ZM20.5 20.5 16 16',
  refresh: 'M20 11a8 8 0 0 0-14.3-4.9L4 8M4 4v4h4M4 13a8 8 0 0 0 14.3 4.9L20 16M20 20v-4h-4',
  plus: 'M12 5v14M5 12h14',
  minus: 'M5 12h14',
  x: 'M6 6l12 12M18 6 6 18',
  check: 'm5 12.5 4.5 4.5L19 7.5',
  arrowRight: 'M5 12h14M13 6l6 6-6 6',
  arrowUpRight: 'M7 17 17 7M8 7h9v9',
  cart: 'M3 4h2.5l2.2 11h10.6L20.5 7H6.4M9.5 20a1 1 0 1 0 0-2 1 1 0 0 0 0 2ZM17.5 20a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z',
  logout: 'M15 4h3.5A1.5 1.5 0 0 1 20 5.5v13a1.5 1.5 0 0 1-1.5 1.5H15M10 16.5 14.5 12 10 7.5M14.5 12H4',
  menu: 'M4 7h16M4 12h16M4 17h10',
  alert: 'M12 9v4.5M12 17h.01M10.3 3.9 2.6 17.5A2 2 0 0 0 4.3 20.5h15.4a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z',
  clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM12 7v5l3 2',
  sparkle: 'M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6',
  wallet: 'M4 7.5A2.5 2.5 0 0 1 6.5 5H18v3M4 7.5V18a2 2 0 0 0 2 2h14V9H6.5A2.5 2.5 0 0 1 4 7.5ZM16.5 14.5h.01',
  shield: 'M12 21s7.5-3.4 7.5-9.5V5.5L12 3 4.5 5.5v6C4.5 17.6 12 21 12 21ZM9 12l2 2 4-4',
  warehouse: 'M3 20V9l9-5 9 5v11M7 20v-7h10v7M7 16h10',
  info: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM12 11v5M12 7.5h.01',
  trash: 'M4.5 7h15M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3',
  calendar: 'M4 6h16v14H4zM4 10h16M8 3v4M16 3v4',
  fuel: 'M5 20V5a1 1 0 0 1 1-1h7a1 1 0 0 1 1 1v15M3.5 20h12M5 10h9M14 8.5l3 1.5v7a1.5 1.5 0 0 0 3 0V9l-3-3',
  weight: 'M6.5 8h11l2 12h-15zM9.5 8a2.5 2.5 0 1 1 5 0',
  building: 'M4 21V6l8-3 8 3v15M9 21v-5h6v5M8 9.5h2M14 9.5h2M8 13h2M14 13h2',
  idcard: 'M3 5.5h18v13H3zM7.5 11.5a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM4.5 16a3 3 0 0 1 6 0M13 9h5M13 12.5h5',
}

export function Icon({ name, className = 'size-5', strokeWidth = 1.75 }) {
  return (
    <svg aria-hidden="true" className={`shrink-0 ${className}`} fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={strokeWidth} viewBox="0 0 24 24">
      <path d={ICON_PATHS[name] ?? ICON_PATHS.grid} />
    </svg>
  )
}

export function BrandMark({ className = 'size-10' }) {
  return (
    <span className={`grid place-items-center rounded-[0.8rem] bg-lime text-ink ${className}`} aria-hidden="true">
      <svg viewBox="0 0 32 32" className="size-[62%]" fill="none">
        <path d="M8 23c7 0 2.5-14 16-14" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
        <circle cx="8" cy="23" r="3.2" fill="currentColor" />
        <circle cx="24" cy="9" r="3.2" fill="currentColor" />
      </svg>
    </span>
  )
}

export function Wordmark({ className = 'text-xl', tone = 'light' }) {
  return (
    <span className={`font-display font-bold tracking-tight ${tone === 'dark' ? 'text-ink' : 'text-paper'} ${className}`}>
      LogiTrack<span className="text-lime-deep">.</span>
    </span>
  )
}

/** Editorial page header: eyebrow, oversized title with an optional italic accent, and actions. */
export function PageHeader({ eyebrow, title, accent, description, actions, children }) {
  return (
    <header className="animate-rise flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
      <div className="max-w-3xl">
        {eyebrow && (
          <p className="eyebrow inline-flex items-center gap-2 text-stone">
            <span className="size-2 rounded-full bg-lime ring-2 ring-ink/80" aria-hidden="true" />
            {eyebrow}
          </p>
        )}
        <h1 className="font-display mt-3 text-[2.6rem] leading-[0.95] font-semibold text-ink sm:text-6xl">
          {title}
          {accent && <> <span className="font-serif-accent text-graphite">{accent}</span></>}
        </h1>
        {description && <p className="mt-4 max-w-2xl text-base leading-7 text-stone">{description}</p>}
        {children}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  )
}

const TILE_TONES = {
  paper: 'bg-paper text-ink border border-line',
  ink: 'bg-ink text-paper border border-ink on-dark',
  lime: 'bg-lime text-ink border border-lime-deep',
  cream: 'bg-cream text-ink border border-sand',
}

/** A KPI tile. Values are proportional figures in the UI sans (never the display face). */
export function StatTile({ label, value, hint, tone = 'paper', icon, loading, className = '', style }) {
  const muted = tone === 'ink' ? 'text-paper/60' : 'text-stone'
  return (
    <article style={style} className={`animate-rise relative overflow-hidden rounded-[1.4rem] p-5 shadow-[var(--shadow-card)] sm:p-6 ${TILE_TONES[tone]} ${className}`}>
      <div className="flex items-start justify-between gap-3">
        <p className={`eyebrow ${muted}`}>{label}</p>
        {icon && (
          <span className={`grid size-9 place-items-center rounded-full ${tone === 'ink' ? 'bg-lime text-ink' : tone === 'lime' ? 'bg-ink text-lime' : tone === 'cream' ? 'bg-paper text-ink' : 'bg-cream text-ink'}`}>
            <Icon name={icon} className="size-4" />
          </span>
        )}
      </div>
      {loading ? (
        <div className={`mt-6 h-10 w-24 rounded-lg ${tone === 'ink' ? 'bg-paper/10' : 'skeleton'}`} />
      ) : (
        <p className={`mt-6 truncate leading-none font-semibold tracking-[-0.04em] ${String(value).length > 10 ? 'text-[1.75rem]' : String(value).length > 7 ? 'text-[2.1rem]' : 'text-[2.5rem]'}`} title={String(value)}>{value}</p>
      )}
      {hint && <p className={`mt-3 text-sm ${muted}`}>{hint}</p>}
    </article>
  )
}

const STATUS_TONES = {
  good: { pill: 'bg-ok-soft text-ok', dot: 'bg-ok' },
  live: { pill: 'bg-lime-soft text-olive', dot: 'bg-olive' },
  warn: { pill: 'bg-warn-soft text-warn', dot: 'bg-warn' },
  bad: { pill: 'bg-bad-soft text-bad', dot: 'bg-bad' },
  neutral: { pill: 'bg-cream text-graphite', dot: 'bg-mist' },
}

const STATUS_GROUPS = {
  good: ['DELIVERED', 'COMPLETED', 'SUCCESS', 'PAID', 'ACTIVE', 'AVAILABLE'],
  live: ['IN_TRANSIT', 'OUT_FOR_DELIVERY', 'PROCESSING', 'PICKED_UP', 'CONFIRMED', 'SHIPPED', 'IN_PROGRESS', 'DISPATCHED'],
  warn: ['PENDING', 'ISSUED', 'CREATED', 'SCHEDULED', 'MAINTENANCE', 'SERVICE', 'ON_LEAVE', 'UNPAID', 'DUE'],
  bad: ['FAILED', 'CANCELLED', 'INACTIVE', 'OUT_OF_SERVICE', 'OVERDUE'],
}

export function statusTone(status) {
  const normalized = String(status ?? '').toUpperCase()
  return Object.keys(STATUS_GROUPS).find((tone) => STATUS_GROUPS[tone].includes(normalized)) ?? 'neutral'
}

/** Status pill: tone + dot + text label, so state is never conveyed by colour alone. */
export function StatusBadge({ status, label }) {
  const tone = STATUS_TONES[statusTone(status)]
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold whitespace-nowrap ${tone.pill}`}>
      <span className={`size-1.5 rounded-full ${tone.dot}`} aria-hidden="true" />
      {label ?? formatLabel(status, 'Unknown')}
    </span>
  )
}

export function Panel({ title, eyebrow, subtitle, actions, children, className = '', bodyClassName = 'p-5 sm:p-6', style }) {
  const hasHead = title || eyebrow || actions
  return (
    <section style={style} className={`panel animate-rise overflow-hidden ${className}`}>
      {hasHead && (
        <div className="flex flex-col gap-3 border-b border-line px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <div className="min-w-0">
            {eyebrow && <p className="eyebrow text-stone">{eyebrow}</p>}
            {title && <h2 className="font-display mt-1 text-xl font-semibold text-ink">{title}</h2>}
            {subtitle && <p className="mt-1 text-sm text-stone">{subtitle}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </div>
      )}
      <div className={bodyClassName}>{children}</div>
    </section>
  )
}

export function RefreshButton({ onClick, loading, label = 'Refresh' }) {
  return (
    <button type="button" onClick={onClick} disabled={loading} className="btn btn-outline">
      <Icon name="refresh" className={`size-4 ${loading ? 'animate-spin' : ''}`} />
      {loading ? 'Refreshing…' : label}
    </button>
  )
}

export function SearchField({ value, onChange, placeholder, label, className = '' }) {
  return (
    <label className={`relative block ${className}`}>
      <span className="sr-only">{label}</span>
      <Icon name="search" className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-mist" />
      <input type="search" value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} aria-label={label} className="field rounded-full! pl-10" />
    </label>
  )
}

export function FilterChips({ options, value, onChange, label }) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap gap-2">
      {options.map((option) => (
        <button key={option.value} type="button" aria-pressed={value === option.value} onClick={() => onChange(option.value)} className="chip">
          {option.label}
          {option.count !== undefined && <span className={`rounded-full px-1.5 text-[0.7rem] ${value === option.value ? 'bg-lime text-ink' : 'bg-cream text-stone'}`}>{option.count}</span>}
        </button>
      ))}
    </div>
  )
}

export function EmptyState({ icon = 'box', title, text, action }) {
  return (
    <div className="flex flex-col items-center px-6 py-14 text-center">
      <span className="relative grid size-16 place-items-center rounded-[1.4rem] bg-cream text-ink">
        <Icon name={icon} className="size-7" strokeWidth={1.5} />
        <span className="absolute -top-1 -right-1 size-4 rounded-full bg-lime ring-4 ring-paper" aria-hidden="true" />
      </span>
      <h3 className="font-display mt-5 text-xl font-semibold text-ink">{title}</h3>
      {text && <p className="mt-2 max-w-sm text-sm leading-6 text-stone">{text}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}

export function ErrorState({ title = 'Something went wrong', message, onRetry }) {
  return (
    <div role="alert" className="flex flex-col items-center px-6 py-12 text-center">
      <span className="grid size-14 place-items-center rounded-2xl bg-bad-soft text-bad"><Icon name="alert" className="size-6" /></span>
      <h3 className="font-display mt-4 text-lg font-semibold text-ink">{title}</h3>
      {message && <p className="mt-1 max-w-md text-sm leading-6 text-stone">{message}</p>}
      {onRetry && <button type="button" onClick={onRetry} className="btn btn-ink mt-5"><Icon name="refresh" className="size-4" />Try again</button>}
    </div>
  )
}

const NOTICE_TONES = {
  error: 'border-[#e8c2b6] bg-bad-soft text-bad',
  success: 'border-[#bcdcc7] bg-ok-soft text-ok',
  info: 'border-lime-deep/50 bg-lime-soft text-olive',
}

export function Notice({ tone = 'info', children, onRetry, role }) {
  return (
    <div role={role ?? (tone === 'error' ? 'alert' : 'status')} className={`animate-rise flex flex-col gap-3 rounded-2xl border px-4 py-3.5 text-sm leading-6 sm:flex-row sm:items-center sm:justify-between ${NOTICE_TONES[tone]}`}>
      <div className="flex items-start gap-2.5">
        <Icon name={tone === 'error' ? 'alert' : tone === 'success' ? 'check' : 'info'} className="mt-0.5 size-4" />
        <div>{children}</div>
      </div>
      {onRetry && <button type="button" onClick={onRetry} className="btn btn-outline shrink-0 py-1.5! text-ink">Try again</button>}
    </div>
  )
}

export function SkeletonRows({ rows = 4, height = 'h-14', label = 'Loading' }) {
  return (
    <div className="space-y-3 p-5 sm:p-6" aria-label={label} aria-busy="true">
      {Array.from({ length: rows }, (_, index) => <div key={index} className={`skeleton ${height}`} style={{ opacity: 1 - index * 0.15 }} />)}
    </div>
  )
}

export function DataTable({ head, minWidth = 720, children, caption }) {
  return (
    <div className="scrollbar-thin overflow-x-auto">
      <table className="data-table" style={{ minWidth }}>
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead><tr>{head.map((cell) => <th key={cell} scope="col">{cell}</th>)}</tr></thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  )
}

export function IdTag({ children, prefix = '#' }) {
  return <span className="font-mono text-[0.8125rem] font-semibold text-ink">{prefix}{children ?? '—'}</span>
}

export function Avatar({ text, className = 'size-10', tone = 'lime' }) {
  const tones = { lime: 'bg-lime text-ink', ink: 'bg-ink text-lime', cream: 'bg-cream text-ink' }
  return <span className={`grid shrink-0 place-items-center rounded-full font-display text-sm font-bold ${tones[tone]} ${className}`} aria-hidden="true">{text}</span>
}

/** Apply staggered entrance delays to grid children. */
export function stagger(index, step = 60) {
  return { animationDelay: `${index * step}ms` }
}


/** Right-hand detail panel. Closes on Escape or a click on the backdrop. */
export function Drawer({ open, title, eyebrow, onClose, children, wide = false }) {
  useEffect(() => {
    if (!open) return undefined
    const onKey = (event) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50">
      <button type="button" aria-label="Close details" className="animate-fade absolute inset-0 bg-ink/50" onClick={onClose} />
      <aside role="dialog" aria-modal="true" aria-label={title} className={`animate-rise absolute inset-y-0 right-0 flex w-full flex-col bg-ivory shadow-[var(--shadow-lift)] ${wide ? 'max-w-3xl' : 'max-w-xl'}`}>
        <div className="on-dark flex items-start justify-between gap-4 bg-ink px-6 py-5 text-paper">
          <div className="min-w-0">
            {eyebrow && <p className="eyebrow text-lime">{eyebrow}</p>}
            <h2 className="font-display mt-1 truncate text-2xl font-semibold">{title}</h2>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="grid size-10 shrink-0 place-items-center rounded-full text-paper/70 hover:bg-paper/10"><Icon name="x" className="size-5" /></button>
        </div>
        <div className="scrollbar-thin flex-1 overflow-y-auto p-5 sm:p-6">{children}</div>
      </aside>
    </div>
  )
}

export function Pagination({ page, pages, total, pageSize, onPage }) {
  if (!total) return null
  const from = (page - 1) * pageSize + 1
  const to = Math.min(total, page * pageSize)
  return (
    <nav aria-label="Pagination" className="flex flex-col items-center justify-between gap-3 border-t border-line px-5 py-3 text-sm sm:flex-row sm:px-6">
      <p className="text-stone" aria-live="polite">Showing {from}–{to} of {total}</p>
      <div className="flex items-center gap-2">
        <button type="button" className="btn btn-outline py-1.5!" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</button>
        <span className="eyebrow text-stone">Page {page} of {Math.max(1, pages)}</span>
        <button type="button" className="btn btn-outline py-1.5!" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next</button>
      </div>
    </nav>
  )
}
