
import { useState } from 'react'
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
const ROLE_NAMES = {
  1: 'ADMIN',
  2: 'OPERATIONS_MANAGER',
  3: 'DRIVER',
  4: 'CUSTOMER',
}

const NAVIGATION = [
  { id: 'dashboard', label: 'Dashboard', roles: [1, 2, 3, 4], icon: 'grid' },
  { id: 'profile', label: 'My profile', roles: [1, 2, 3, 4], icon: 'users' },
  { id: 'orders', label: 'Orders', roles: [1, 2, 4], icon: 'box' },
  { id: 'shipments', label: 'Shipments', roles: [1, 2, 3, 4], icon: 'route' },
  { id: 'tracking', label: 'Tracking', roles: [1, 2, 3, 4], icon: 'pin' },
  { id: 'deliveries', label: 'Deliveries', roles: [1, 2, 3, 4], icon: 'truck' },
  { id: 'vehicles', label: 'Vehicles', roles: [1, 2], icon: 'vehicle' },
  { id: 'drivers', label: 'Drivers', roles: [1, 2], icon: 'users' },
  { id: 'payments', label: 'Payments', roles: [1, 2, 4], icon: 'card' },
  { id: 'invoices', label: 'Invoices', roles: [1, 2, 4], icon: 'file' },
  { id: 'analytics', label: 'Analytics', roles: [1, 2], icon: 'chart' },
  { id: 'users', label: 'Users', roles: [1], icon: 'users' },
]

function AppShell({ session, onLogout }) {
  const roleId = Number(session.user.roleId)
  const [displayUsername, setDisplayUsername] = useState(session.user.username)
  const activeSession = { ...session, user: { ...session.user, username: displayUsername } }

  const navItems = NAVIGATION.filter((item) =>
    item.roles.includes(roleId)
  )

  const [activePage, setActivePage] = useState('dashboard')
  const [mobileNavOpen, setMobileNavOpen] = useState(false)

  const currentPage =
    navItems.find((item) => item.id === activePage) ?? navItems[0]

  const workspaceName =
    roleId === 4
      ? 'Customer workspace'
      : roleId === 3
        ? 'Driver workspace'
        : roleId === 2
          ? 'Operations workspace'
          : 'Administration workspace'

  function selectPage(pageId) {
    setActivePage(pageId)
    setMobileNavOpen(false)
  }

  return (
    <div className="min-h-screen bg-slate-100 text-slate-950">
      {mobileNavOpen && (
        <button
          aria-label="Close navigation"
          className="fixed inset-0 z-30 bg-slate-950/40 lg:hidden"
          onClick={() => setMobileNavOpen(false)}
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-72 flex-col bg-slate-950 p-5 text-slate-300 shadow-2xl transition-transform lg:translate-x-0 ${
          mobileNavOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex items-center gap-3 px-2">
          <BrandMark />
          <span className="text-xl font-semibold tracking-tight text-white">
            LogiTrack
          </span>
        </div>

        <nav
          aria-label="Main navigation"
          className="mt-10 flex-1 space-y-1"
        >
          <p className="px-3 pb-3 text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
            Workspace
          </p>

          {navItems.map((item) => (
            <button
              className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm font-medium transition ${
                activePage === item.id
                  ? 'bg-cyan-400 text-slate-950'
                  : 'hover:bg-slate-800 hover:text-white'
              }`}
              key={item.id}
              onClick={() => selectPage(item.id)}
            >
              <NavIcon name={item.icon} />
              {item.label}
            </button>
          ))}
        </nav>

        <div className="rounded-xl border border-slate-800 bg-slate-900 p-3">
          <p className="truncate text-sm font-semibold text-white">
            {activeSession.user.username}
          </p>
          <p className="mt-1 text-xs font-medium text-cyan-300">
            {ROLE_NAMES[roleId] ?? 'USER'}
          </p>
        </div>
      </aside>

      <div className="lg:pl-72">
        <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-slate-200 bg-white/95 px-4 backdrop-blur sm:px-7">
          <div className="flex items-center gap-3">
            <button
              aria-label="Open navigation"
              className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 lg:hidden"
              onClick={() => setMobileNavOpen(true)}
            >
              <MenuIcon />
            </button>

            <div>
              <p className="text-xs font-medium text-slate-500">
                {workspaceName}
              </p>
              <h1 className="font-semibold text-slate-900">
                {currentPage?.label ?? 'Dashboard'}
              </h1>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="hidden text-right sm:block">
              <p className="text-sm font-semibold text-slate-800">
                {activeSession.user.username}
              </p>
              <p className="text-xs text-slate-500">
                {ROLE_NAMES[roleId] ?? 'USER'}
              </p>
            </div>

            <button
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700 transition hover:border-slate-400 hover:bg-slate-50"
              onClick={onLogout}
            >
              Log out
            </button>
          </div>
        </header>

        <section className="p-4 sm:p-7">
          {currentPage?.id === 'dashboard' ? (
            <Dashboard
              session={activeSession}
              onAuthExpired={onLogout}
            />
          ) : currentPage?.id === 'orders' ? (
            <Orders
              session={session}
              onAuthExpired={onLogout}
            />
          ) : currentPage?.id === 'shipments' ? (
            <Shipments
              session={session}
              onAuthExpired={onLogout}
            />
          ) : currentPage?.id === 'tracking' ? (
            <Tracking
              session={session}
              onAuthExpired={onLogout}
            />
                    ) : currentPage?.id === 'deliveries' ? (
            <Deliveries
              session={session}
              onAuthExpired={onLogout}
            />
                    ) : currentPage?.id === 'payments' ? (
            <Payments
              session={session}
              onAuthExpired={onLogout}
            />
          ) : currentPage?.id === 'invoices' ? (
            <Invoices
              session={session}
              onAuthExpired={onLogout}
            />
          ) : currentPage?.id === 'vehicles' ? (
            <Vehicles
              session={session}
              onAuthExpired={onLogout}
            />
          ) : currentPage?.id === 'drivers' ? (
            <Drivers
              session={session}
              onAuthExpired={onLogout}
            />
          ) : currentPage?.id === 'analytics' ? (
            <Analytics
              session={session}
              onAuthExpired={onLogout}
            />
          ) : currentPage?.id === 'profile' ? (
            <Profile
              session={activeSession}
              onAuthExpired={onLogout}
              onUsernameUpdated={setDisplayUsername}
              onPasswordChanged={onLogout}
            />
          ) : currentPage?.id === 'users' ? (
            <Users
              session={session}
              onAuthExpired={onLogout}
            />
          ) : (
            <PagePlaceholder
              page={currentPage}
              roleName={ROLE_NAMES[roleId]}
            />
          )}
        </section>
      </div>
    </div>
  )
}

function BrandMark() {
  return (
    <span className="grid size-10 place-items-center rounded-xl bg-cyan-400 text-slate-950">
      <NavIcon name="truck" />
    </span>
  )
}

function MenuIcon() {
  return (
    <svg
      aria-hidden="true"
      className="size-5"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      viewBox="0 0 24 24"
    >
      <path strokeLinecap="round" d="M4 7h16M4 12h16M4 17h16" />
    </svg>
  )
}

function NavIcon({ name }) {
  const paths = {
    grid: 'M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z',
    box: 'm4 7 8-4 8 4v10l-8 4-8-4zM4 7l8 4 8-4M12 11v10',
    route: 'M5 19c7 0 2-14 14-14M16 2l3 3-3 3M5 19h.01',
    pin: 'M12 21s6-5.1 6-11a6 6 0 1 0-12 0c0 5.9 6 11 6 11ZM12 10h.01',
    truck: 'M3 6h11v11H3zM14 9h3l4 4v4h-7zM7 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM18 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z',
    vehicle: 'M4 15l1.5-5h13l1.5 5M3 15h18v4H3zM7 19a1 1 0 1 0 0-2 1 1 0 0 0 0 2ZM17 19a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z',
    users: 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75',
    card: 'M3 6h18v12H3zM3 10h18M7 15h3',
    file: 'M6 3h8l4 4v14H6zM14 3v5h5M9 13h6M9 17h6',
    chart: 'M4 20V10M10 20V4M16 20v-7M22 20H2',
  }

  return (
    <svg
      aria-hidden="true"
      className="size-5 shrink-0"
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.8"
      viewBox="0 0 24 24"
    >
      <path d={paths[name] ?? paths.grid} />
    </svg>
  )
}

export default AppShell
