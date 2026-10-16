import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError, apiGet } from '../services/apiClient.js'

function formatLabel(value) {
  if (!value) return '-'
  return String(value).replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function formatDate(value) {
  if (!value) return '-'
  const date = new Date(value)
  return Number.isNaN(date.valueOf()) ? String(value) : new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }).format(date)
}

function StatusBadge({ status }) {
  const value = String(status ?? 'UNKNOWN')
  const normalized = value.toUpperCase()
  const tone = ['AVAILABLE', 'ACTIVE'].includes(normalized)
    ? 'bg-emerald-50 text-emerald-700 ring-emerald-600/20'
    : normalized.includes('ON_LEAVE') || normalized.includes('INACTIVE')
      ? 'bg-rose-50 text-rose-700 ring-rose-600/20'
      : 'bg-amber-50 text-amber-700 ring-amber-600/20'
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset ${tone}`}>{formatLabel(value)}</span>
}

function SummaryCard({ label, value, detail }) {
  return <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><p className="text-sm font-medium text-slate-500">{label}</p><p className="mt-3 text-2xl font-bold tracking-tight text-slate-950">{value}</p><p className="mt-1 text-xs text-slate-500">{detail}</p></article>
}

function Drivers({ session, onAuthExpired }) {
  const [drivers, setDrivers] = useState([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')

  const loadDrivers = useCallback(async (isRefresh = false) => {
    isRefresh ? setRefreshing(true) : setLoading(true)
    setError('')
    try {
      const data = await apiGet('/drivers', session.accessToken)
      if (!Array.isArray(data)) throw new Error('Unexpected response from the drivers API.')
      setDrivers(data)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onAuthExpired()
        return
      }
      setError(err instanceof ApiError && err.status === 403 ? 'You do not have permission to view drivers.' : err.message || 'Unable to load drivers.')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [session.accessToken, onAuthExpired])

  useEffect(() => { loadDrivers() }, [loadDrivers])

  const filteredDrivers = useMemo(() => {
    const query = search.trim().toLowerCase()
    if (!query) return drivers
    return drivers.filter((driver) => [driver.employee_id, driver.name, driver.phone, driver.department, driver.license_no, driver.availability_status, driver.employment_status].some((value) => String(value ?? '').toLowerCase().includes(query)))
  }, [drivers, search])

  const availableCount = drivers.filter((driver) => String(driver.availability_status ?? '').toUpperCase() === 'AVAILABLE').length
  const activeEmployees = drivers.filter((driver) => String(driver.employment_status ?? '').toUpperCase() === 'ACTIVE').length

  return <div className="mx-auto max-w-7xl space-y-6">
    <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="text-sm font-medium text-cyan-700">Fleet operations</p><h2 className="mt-1 text-2xl font-bold tracking-tight text-slate-950">Drivers</h2><p className="mt-2 text-sm text-slate-500">Review driver profiles, licence details, and availability.</p></div><button type="button" onClick={() => loadDrivers(true)} disabled={loading || refreshing} className="inline-flex items-center justify-center rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60">{refreshing ? 'Refreshing...' : 'Refresh drivers'}</button></div>
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3"><SummaryCard label="Total drivers" value={loading ? '-' : drivers.length} detail="Driver profiles available" /><SummaryCard label="Available" value={loading ? '-' : availableCount} detail="Ready for assignment" /><SummaryCard label="Active employees" value={loading ? '-' : activeEmployees} detail="Employment status: active" /></div>
    {error && <div role="alert" className="flex flex-col gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 sm:flex-row sm:items-center sm:justify-between"><p className="text-sm text-rose-700">{error}</p><button type="button" onClick={() => loadDrivers()} className="shrink-0 rounded-lg border border-rose-200 bg-white px-3 py-2 text-sm font-semibold text-rose-700 hover:bg-rose-100">Try again</button></div>}
    <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"><div className="flex flex-col gap-3 border-b border-slate-200 p-5 sm:flex-row sm:items-center sm:justify-between"><div><h3 className="font-semibold text-slate-900">Driver records</h3><p className="mt-1 text-sm text-slate-500">{loading ? 'Loading driver records...' : `${filteredDrivers.length} record${filteredDrivers.length === 1 ? '' : 's'} found`}</p></div><input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search drivers..." aria-label="Search drivers" className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm outline-none transition placeholder:text-slate-400 focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100 sm:max-w-xs" /></div>
      {loading ? <div className="space-y-3 p-5" aria-label="Loading drivers">{[1, 2, 3, 4].map((item) => <div key={item} className="h-12 animate-pulse rounded-lg bg-slate-100" />)}</div>
        : error ? <div className="p-10 text-center"><p className="font-medium text-slate-700">Driver records could not be loaded.</p><p className="mt-1 text-sm text-slate-500">Resolve the error above and try again.</p></div>
          : filteredDrivers.length === 0 ? <div className="px-5 py-14 text-center"><h3 className="font-semibold text-slate-900">{search ? 'No matching drivers' : 'No drivers yet'}</h3><p className="mx-auto mt-1 max-w-sm text-sm text-slate-500">{search ? 'Try a driver name, ID, licence number, or status.' : 'Driver records will appear here when available.'}</p></div>
            : <div className="overflow-x-auto"><table className="w-full min-w-[1050px] text-left text-sm"><thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500"><tr><th className="px-5 py-3 font-semibold">Driver</th><th className="px-5 py-3 font-semibold">Employee ID</th><th className="px-5 py-3 font-semibold">Phone</th><th className="px-5 py-3 font-semibold">Department</th><th className="px-5 py-3 font-semibold">Licence</th><th className="px-5 py-3 font-semibold">Expires</th><th className="px-5 py-3 font-semibold">Availability</th><th className="px-5 py-3 font-semibold">Employment</th></tr></thead><tbody className="divide-y divide-slate-100">{filteredDrivers.map((driver, index) => <tr key={driver.employee_id ?? index} className="transition hover:bg-slate-50"><td className="whitespace-nowrap px-5 py-4 font-semibold text-slate-900">{driver.name ?? '-'}</td><td className="whitespace-nowrap px-5 py-4 text-slate-600">#{driver.employee_id ?? '-'}</td><td className="whitespace-nowrap px-5 py-4 text-slate-600">{driver.phone ?? '-'}</td><td className="whitespace-nowrap px-5 py-4 text-slate-600">{formatLabel(driver.department)}</td><td className="whitespace-nowrap px-5 py-4 text-slate-600">{driver.license_no ?? '-'}</td><td className="whitespace-nowrap px-5 py-4 text-slate-600">{formatDate(driver.license_expiry)}</td><td className="whitespace-nowrap px-5 py-4"><StatusBadge status={driver.availability_status} /></td><td className="whitespace-nowrap px-5 py-4"><StatusBadge status={driver.employment_status} /></td></tr>)}</tbody></table></div>}
    </section>
  </div>
}

export default Drivers
