import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError, apiGet } from '../services/apiClient.js'
import { formatDate, formatLabel, initials } from '../lib/format.js'
import { BarList } from './charts.jsx'
import { Avatar, DataTable, EmptyState, ErrorState, Notice, PageHeader, Panel, RefreshButton, SearchField, SkeletonRows, StatTile, StatusBadge, stagger } from './ui.jsx'

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
  const roleCounts = users.reduce((counts, user) => {
    const role = user.role_name ?? `Role #${user.role_id}`
    return { ...counts, [role]: (counts[role] ?? 0) + 1 }
  }, {})
  const roleItems = Object.entries(roleCounts).sort((a, b) => b[1] - a[1]).map(([role, count]) => ({ key: role, label: formatLabel(role), value: count }))

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Administration"
        title="People"
        accent="& access."
        description="Review account records and access roles. This page is read-only."
        actions={<RefreshButton onClick={() => loadUsers(true)} loading={loading || refreshing} label="Refresh users" />}
      />

      <div className="grid gap-4 lg:grid-cols-[1fr_1fr_1.5fr]">
        <StatTile label="Total users" value={loading ? '—' : users.length} hint="Account records available" icon="users" loading={loading} />
        <StatTile label="Active accounts" value={loading ? '—' : activeCount} hint={users.length ? `${users.length - activeCount} inactive` : 'Currently active'} icon="shield" tone="lime" loading={loading} style={stagger(1)} />
        <Panel eyebrow="Access" title={`${roleItems.length} role${roleItems.length === 1 ? '' : 's'} in use`} style={stagger(2)}>
          {roleItems.length ? <BarList items={roleItems} caption="Users by role" /> : <p className="text-sm text-stone">{loading ? 'Loading…' : 'No roles yet.'}</p>}
        </Panel>
      </div>

      {error && <Notice tone="error" onRetry={() => loadUsers()}>{error}</Notice>}

      <Panel
        bodyClassName="p-0"
        title="User records"
        subtitle={loading ? 'Loading user records…' : `${filteredUsers.length} record${filteredUsers.length === 1 ? '' : 's'} found`}
        actions={<SearchField value={search} onChange={setSearch} placeholder="Username, email, or role…" label="Search users" className="w-full sm:w-72" />}
      >
        {loading ? <SkeletonRows rows={4} label="Loading users" />
          : error ? <ErrorState title="User records could not be loaded" message="Resolve the error above and try again." />
            : filteredUsers.length === 0 ? <EmptyState icon="users" title={search ? 'No matching users' : 'No users yet'} text={search ? 'Try another username, email address, or role.' : 'User records will appear here when available.'} />
              : (
                <DataTable head={['User', 'Email', 'Role', 'Created', 'Status']} minWidth={820} caption="Users">
                  {filteredUsers.map((user) => (
                    <tr key={user.user_id}>
                      <td>
                        <div className="flex items-center gap-3">
                          <Avatar text={initials(user.username)} className="size-9 text-xs" tone={user.is_active ? 'lime' : 'cream'} />
                          <div>
                            <p className="font-semibold text-ink">{user.username}</p>
                            <p className="font-mono text-xs text-stone">ID #{user.user_id}</p>
                          </div>
                        </div>
                      </td>
                      <td>{user.email}</td>
                      <td><span className="eyebrow rounded-full bg-cream px-2.5 py-1 text-graphite">{user.role_name ? formatLabel(user.role_name) : `Role #${user.role_id}`}</span></td>
                      <td>{formatDate(user.created_at)}</td>
                      <td><StatusBadge status={user.is_active ? 'ACTIVE' : 'INACTIVE'} /></td>
                    </tr>
                  ))}
                </DataTable>
              )}
      </Panel>
    </div>
  )
}

export default Users
