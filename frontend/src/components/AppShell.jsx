import { useEffect, useState } from 'react'
import Dashboard from './Dashboard.jsx'
import PagePlaceholder from './PagePlaceholder.jsx'
import Orders from './Orders.jsx'
import Shipments from './Shipments.jsx'
import Tracking from './Tracking.jsx'
import Deliveries from './Deliveries.jsx'
import Payments from './Payments.jsx'
import Invoices from './Invoices.jsx'
import Vehicles from './Vehicles.jsx'
import Drivers from './Drivers.jsx'
import Analytics from './Analytics.jsx'
import Profile from './Profile.jsx'
import Users from './Users.jsx'
import Shop from './Shop.jsx'
import { Avatar, BrandMark, Icon, Wordmark } from './ui.jsx'
import { ROLE_NAMES, formatLabel, initials } from '../lib/format.js'

const NAVIGATION = [
  { id: 'dashboard', label: 'Dashboard', roles: [1, 2, 3, 4], icon: 'grid', group: 'Overview' },
  { id: 'shop', label: 'Shop', roles: [4], icon: 'shop', group: 'Commerce' },
  { id: 'orders', label: 'Orders', roles: [1, 2, 4], icon: 'box', group: 'Commerce' },
  { id: 'shipments', label: 'Shipments', roles: [1, 2, 3, 4], icon: 'route', group: 'Logistics' },
  { id: 'tracking', label: 'Tracking', roles: [1, 2, 3, 4], icon: 'pin', group: 'Logistics' },
  { id: 'deliveries', label: 'Deliveries', roles: [1, 2, 3, 4], icon: 'truck', group: 'Logistics' },
  { id: 'vehicles', label: 'Vehicles', roles: [1, 2], icon: 'vehicle', group: 'Fleet' },
  { id: 'drivers', label: 'Drivers', roles: [1, 2], icon: 'users', group: 'Fleet' },
  { id: 'payments', label: 'Payments', roles: [1, 2, 4], icon: 'card', group: 'Finance' },
  { id: 'invoices', label: 'Invoices', roles: [1, 2, 4], icon: 'file', group: 'Finance' },
  { id: 'analytics', label: 'Analytics', roles: [1, 2], icon: 'chart', group: 'Insight' },
  { id: 'users', label: 'Users', roles: [1], icon: 'shield', group: 'Administration' },
  { id: 'profile', label: 'My profile', roles: [1, 2, 3, 4], icon: 'user', group: 'Account' },
]

const WORKSPACES = { 1: 'Administration', 2: 'Operations', 3: 'Driver', 4: 'Customer' }

function AppShell({ session, onLogout }) {
  const roleId = Number(session.user.roleId)
  const [displayUsername, setDisplayUsername] = useState(session.user.username)
  const activeSession = { ...session, user: { ...session.user, username: displayUsername } }

  const navItems = NAVIGATION.filter((item) => item.roles.includes(roleId))
  const groups = [...new Set(navItems.map((item) => item.group))]

  const [activePage, setActivePage] = useState(roleId === 4 ? 'shop' : 'dashboard')
  const [mobileNavOpen, setMobileNavOpen] = useState(false)

  const currentPage = navItems.find((item) => item.id === activePage) ?? navItems[0]
  const roleLabel = formatLabel(ROLE_NAMES[roleId] ?? 'USER')

  useEffect(() => {
    if (!mobileNavOpen) return undefined
    const closeOnEscape = (event) => { if (event.key === 'Escape') setMobileNavOpen(false) }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [mobileNavOpen])

  function selectPage(pageId) {
    if (!navItems.some((item) => item.id === pageId)) return
    setActivePage(pageId)
    setMobileNavOpen(false)
    window.scrollTo({ top: 0 })
  }

  const pageProps = { session, onAuthExpired: onLogout, onNavigate: selectPage }

  return (
    <div className="min-h-screen text-ink">
      <a href="#main-content" className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-[60] focus:rounded-full focus:bg-lime focus:px-4 focus:py-2 focus:font-semibold">Skip to content</a>

      {mobileNavOpen && (
        <button aria-label="Close navigation" className="animate-fade fixed inset-0 z-30 bg-ink/50 lg:hidden" onClick={() => setMobileNavOpen(false)} />
      )}

      <aside
        id="app-sidebar"
        className={`on-dark fixed inset-y-0 left-0 z-40 flex w-[17.5rem] flex-col bg-ink text-paper/70 transition-transform duration-300 ease-out lg:translate-x-0 ${mobileNavOpen ? 'translate-x-0' : '-translate-x-full'}`}
      >
        <div className="flex items-center justify-between px-6 pt-6">
          <div className="flex items-center gap-3">
            <BrandMark className="size-10" />
            <div>
              <Wordmark className="text-[1.35rem]" />
              <p className="eyebrow mt-0.5 text-paper/40">{WORKSPACES[roleId]} workspace</p>
            </div>
          </div>
          <button type="button" aria-label="Close navigation" onClick={() => setMobileNavOpen(false)} className="rounded-full p-2 text-paper/60 hover:bg-paper/10 hover:text-paper lg:hidden">
            <Icon name="x" className="size-5" />
          </button>
        </div>

        <nav aria-label="Main navigation" className="scrollbar-thin mt-8 flex-1 overflow-y-auto px-4 pb-6">
          {groups.map((group) => (
            <div key={group} className="mb-5">
              <p className="eyebrow px-3 pb-2 text-paper/35">{group}</p>
              <ul className="space-y-0.5">
                {navItems.filter((item) => item.group === group).map((item) => {
                  const active = currentPage?.id === item.id
                  return (
                    <li key={item.id}>
                      <button
                        type="button"
                        aria-current={active ? 'page' : undefined}
                        onClick={() => selectPage(item.id)}
                        className={`group flex w-full items-center gap-3 rounded-full px-3 py-2.5 text-left text-sm font-medium transition-colors ${active ? 'bg-lime text-ink' : 'hover:bg-paper/[0.06] hover:text-paper'}`}
                      >
                        <span className={`grid size-8 place-items-center rounded-full transition-colors ${active ? 'bg-ink text-lime' : 'bg-paper/[0.06] text-paper/70 group-hover:text-lime'}`}>
                          <Icon name={item.icon} className="size-[1.05rem]" />
                        </span>
                        {item.label}
                        {active && <Icon name="arrowRight" className="ml-auto size-4" />}
                      </button>
                    </li>
                  )
                })}
              </ul>
            </div>
          ))}
        </nav>

        <div className="m-4 mt-0 rounded-[1.25rem] border border-paper/10 bg-paper/[0.04] p-3">
          <div className="flex items-center gap-3">
            <Avatar text={initials(activeSession.user.username)} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold text-paper">{activeSession.user.username}</p>
              <p className="truncate text-xs text-lime">{roleLabel}</p>
            </div>
            <button type="button" onClick={onLogout} aria-label="Log out" title="Log out" className="grid size-9 place-items-center rounded-full text-paper/60 transition hover:bg-paper/10 hover:text-lime">
              <Icon name="logout" className="size-[1.1rem]" />
            </button>
          </div>
        </div>
      </aside>

      <div className="lg:pl-[17.5rem]">
        <header className="sticky top-0 z-20 border-b border-line bg-ivory/95">
          <div className="mx-auto flex h-16 max-w-[90rem] items-center justify-between gap-4 px-4 sm:px-8">
            <div className="flex min-w-0 items-center gap-3">
              <button type="button" aria-label="Open navigation" aria-controls="app-sidebar" aria-expanded={mobileNavOpen} className="grid size-10 place-items-center rounded-full bg-ink text-lime lg:hidden" onClick={() => setMobileNavOpen(true)}>
                <Icon name="menu" className="size-5" />
              </button>
              <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-2 text-sm">
                <span className="hidden text-stone sm:inline">{WORKSPACES[roleId]}</span>
                <span className="hidden text-mist sm:inline" aria-hidden="true">/</span>
                <span className="truncate font-semibold text-ink">{currentPage?.label ?? 'Dashboard'}</span>
              </nav>
            </div>

            <div className="flex items-center gap-2 sm:gap-3">
              <span className="eyebrow hidden rounded-full bg-paper px-3 py-1.5 text-stone ring-1 ring-line md:inline-flex">
                {new Intl.DateTimeFormat('en-IN', { weekday: 'short', day: 'numeric', month: 'short' }).format(new Date())}
              </span>
              <span className="hidden items-center gap-2 rounded-full bg-ink py-1 pr-3 pl-1 text-xs font-semibold text-paper sm:inline-flex">
                <Avatar text={initials(activeSession.user.username)} className="size-6 text-[0.65rem]" />
                {roleLabel}
              </span>
              <button type="button" className="btn btn-outline px-3.5! py-2!" onClick={onLogout}>
                <Icon name="logout" className="size-4" />
                <span className="hidden sm:inline">Log out</span>
              </button>
            </div>
          </div>
        </header>

        <main id="main-content" tabIndex={-1} className="mx-auto max-w-[90rem] px-4 pt-8 pb-24 outline-none sm:px-8 sm:pt-10">
          <div key={currentPage?.id}>
            {currentPage?.id === 'dashboard' ? (
              <Dashboard {...pageProps} session={activeSession} />
            ) : currentPage?.id === 'orders' ? (
              <Orders {...pageProps} />
            ) : currentPage?.id === 'shop' ? (
              <Shop {...pageProps} />
            ) : currentPage?.id === 'shipments' ? (
              <Shipments {...pageProps} />
            ) : currentPage?.id === 'tracking' ? (
              <Tracking {...pageProps} />
            ) : currentPage?.id === 'deliveries' ? (
              <Deliveries {...pageProps} />
            ) : currentPage?.id === 'payments' ? (
              <Payments {...pageProps} />
            ) : currentPage?.id === 'invoices' ? (
              <Invoices {...pageProps} />
            ) : currentPage?.id === 'vehicles' ? (
              <Vehicles {...pageProps} />
            ) : currentPage?.id === 'drivers' ? (
              <Drivers {...pageProps} />
            ) : currentPage?.id === 'analytics' ? (
              <Analytics {...pageProps} />
            ) : currentPage?.id === 'profile' ? (
              <Profile
                {...pageProps}
                session={activeSession}
                onUsernameUpdated={setDisplayUsername}
                onPasswordChanged={onLogout}
              />
            ) : currentPage?.id === 'users' ? (
              <Users {...pageProps} />
            ) : (
              <PagePlaceholder page={currentPage} roleName={ROLE_NAMES[roleId]} />
            )}
          </div>
        </main>
      </div>
    </div>
  )
}

export default AppShell
