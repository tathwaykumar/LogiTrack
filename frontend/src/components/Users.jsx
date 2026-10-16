import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError, apiGet } from '../services/apiClient.js'

function formatDate(value) {
  if (!value) return '-'
  const date = new Date(value)
  return Number.isNaN(date.valueOf()) ? String(value) : new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }).format(date)
}

function StatusBadge({ active }) {
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset ${active ? 'bg-emerald-50 text-emerald-700 ring-emerald-600/20' : 'bg-slate-100 text-slate-700 ring-slate-500/20'}`}>{active ? 'Active' : 'Inactive'}</span>
}

function SummaryCard({ label, value, detail }) {
  return <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><p className="text-sm font-medium text-slate-500">{label}</p><p className="mt-3 text-2xl font-bold tracking-tight text-slate-950">{value}</p><p className="mt-1 text-xs text-slate-500">{detail}</p></article>
}

function Users({ session, onAuthExpired }) {
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')

  const loadUsers = useCallback(async (isRefresh = false) => {
    isRefresh ? setRefreshing(true) : setLoading(true)
    setError('')
    try {
      const data = await apiGet('/users', session.accessToken)
      if (!Array.isArray(data)) throw new Error('Unexpected response from the users API.')
      setUsers(data)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onAuthExpired()
        return
      }
      setError(err instanceof ApiError && err.status === 403 ? 'You do not have permission to view users.' : err.message || 'Unable to load users.')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [session.accessToken, onAuthExpired])

  useEffect(() => { loadUsers() }, [loadUsers])

  const filteredUsers = useMemo(() => {
    const query = search.trim().toLowerCase()
    if (!query) return users
    return users.filter((user) => [user.username, user.email, user.role_name].some((value) => String(value ?? '').toLowerCase().includes(query)))
  }, [users, search])

  const activeCount = users.filter((user) => user.is_active).length
  const roleCount = new Set(users.map((user) => user.role_name).filter(Boolean)).size

  return <div className="mx-auto max-w-7xl space-y-6">
    <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="text-sm font-medium text-cyan-700">Administration</p><h2 className="mt-1 text-2xl font-bold tracking-tight text-slate-950">Users</h2><p className="mt-2 text-sm text-slate-500">Review account records and access roles. This page is read-only.</p></div><button type="button" onClick={() => loadUsers(true)} disabled={loading || refreshing} className="inline-flex items-center justify-center rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60">{refreshing ? 'Refreshing...' : 'Refresh users'}</button></div>
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3"><SummaryCard label="Total users" value={loading ? '-' : users.length} detail="Account records available" /><SummaryCard label="Active accounts" value={loading ? '-' : activeCount} detail="Currently active" /><SummaryCard label="Roles in use" value={loading ? '-' : roleCount} detail="Across listed users" /></div>
    {error && <div role="alert" className="flex flex-col gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 sm:flex-row sm:items-center sm:justify-between"><p className="text-sm text-rose-700">{error}</p><button type="button" onClick={() => loadUsers()} className="shrink-0 rounded-lg border border-rose-200 bg-white px-3 py-2 text-sm font-semibold text-rose-700 hover:bg-rose-100">Try again</button></div>}
    <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"><div className="flex flex-col gap-3 border-b border-slate-200 p-5 sm:flex-row sm:items-center sm:justify-between"><div><h3 className="font-semibold text-slate-900">User records</h3><p className="mt-1 text-sm text-slate-500">{loading ? 'Loading user records...' : `${filteredUsers.length} record${filteredUsers.length === 1 ? '' : 's'} found`}</p></div><input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search username, email, or role..." aria-label="Search users" className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm outline-none transition placeholder:text-slate-400 focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100 sm:max-w-xs" /></div>
      {loading ? <div className="space-y-3 p-5" aria-label="Loading users">{[1, 2, 3, 4].map((item) => <div key={item} className="h-12 animate-pulse rounded-lg bg-slate-100" />)}</div>
        : error ? <div className="p-10 text-center"><p className="font-medium text-slate-700">User records could not be loaded.</p><p className="mt-1 text-sm text-slate-500">Resolve the error above and try again.</p></div>
          : filteredUsers.length === 0 ? <div className="px-5 py-14 text-center"><h3 className="font-semibold text-slate-900">{search ? 'No matching users' : 'No users yet'}</h3><p className="mx-auto mt-1 max-w-sm text-sm text-slate-500">{search ? 'Try another username, email address, or role.' : 'User records will appear here when available.'}</p></div>
            : <div className="overflow-x-auto"><table className="w-full min-w-[860px] text-left text-sm"><thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500"><tr><th className="px-5 py-3 font-semibold">User ID</th><th className="px-5 py-3 font-semibold">Username</th><th className="px-5 py-3 font-semibold">Email</th><th className="px-5 py-3 font-semibold">Role</th><th className="px-5 py-3 font-semibold">Created</th><th className="px-5 py-3 font-semibold">Status</th></tr></thead><tbody className="divide-y divide-slate-100">{filteredUsers.map((user) => <tr key={user.user_id} className="transition hover:bg-slate-50"><td className="whitespace-nowrap px-5 py-4 font-semibold text-slate-900">#{user.user_id}</td><td className="whitespace-nowrap px-5 py-4 font-medium text-slate-900">{user.username}</td><td className="whitespace-nowrap px-5 py-4 text-slate-600">{user.email}</td><td className="whitespace-nowrap px-5 py-4 text-slate-600">{user.role_name ?? `Role #${user.role_id}`}</td><td className="whitespace-nowrap px-5 py-4 text-slate-600">{formatDate(user.created_at)}</td><td className="whitespace-nowrap px-5 py-4"><StatusBadge active={user.is_active} /></td></tr>)}</tbody></table></div>}
    </section>
  </div>
}

export default Users
