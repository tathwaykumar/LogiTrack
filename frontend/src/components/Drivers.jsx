import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError, apiGet } from '../services/apiClient.js'
import { daysUntil, formatDate, formatLabel, initials } from '../lib/format.js'
import { Avatar, DataTable, EmptyState, ErrorState, Notice, PageHeader, Panel, RefreshButton, SearchField, SkeletonRows, StatTile, StatusBadge, stagger } from './ui.jsx'

function LicenceExpiry({ value }) {
  const days = daysUntil(value)
  if (days === null) return <span>{formatDate(value)}</span>
  const tone = days < 0 ? 'text-bad' : days <= 60 ? 'text-warn' : 'text-stone'
  return (
    <span className="flex flex-col">
      <span className="text-graphite">{formatDate(value)}</span>
      <span className={`text-xs font-semibold ${tone}`}>{days < 0 ? 'Expired' : `${days} days left`}</span>
    </span>
  )
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
  const expiringSoon = drivers.filter((driver) => { const days = daysUntil(driver.license_expiry); return days !== null && days <= 60 }).length

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Fleet operations"
        title="Drivers"
        accent="on the roster."
        description="Review driver profiles, licence details, and availability."
        actions={<RefreshButton onClick={() => loadDrivers(true)} loading={loading || refreshing} label="Refresh drivers" />}
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile label="Total drivers" value={loading ? '—' : drivers.length} icon="users" loading={loading} />
        <StatTile label="Available" value={loading ? '—' : availableCount} hint="Ready for assignment" icon="check" tone="lime" loading={loading} style={stagger(1)} />
        <StatTile label="Active employees" value={loading ? '—' : activeEmployees} hint="Employment status: active" icon="idcard" tone="cream" loading={loading} style={stagger(2)} />
        <StatTile label="Licences ≤ 60 days" value={loading ? '—' : expiringSoon} hint="Expired or expiring soon" icon="alert" tone="ink" loading={loading} style={stagger(3)} />
      </div>

      {error && <Notice tone="error" onRetry={() => loadDrivers()}>{error}</Notice>}

      <Panel
        bodyClassName="p-0"
        title="Driver roster"
        subtitle={loading ? 'Loading driver records…' : `${filteredDrivers.length} record${filteredDrivers.length === 1 ? '' : 's'} found`}
        actions={<SearchField value={search} onChange={setSearch} placeholder="Search drivers…" label="Search drivers" className="w-full sm:w-72" />}
      >
        {loading ? <SkeletonRows rows={4} label="Loading drivers" />
          : error ? <ErrorState title="Driver records could not be loaded" message="Resolve the error above and try again." />
            : filteredDrivers.length === 0 ? <EmptyState icon="users" title={search ? 'No matching drivers' : 'No drivers yet'} text={search ? 'Try a driver name, ID, licence number, or status.' : 'Driver records will appear here when available.'} />
              : (
                <DataTable head={['Driver', 'Phone', 'Department', 'Licence', 'Expires', 'Availability', 'Employment']} minWidth={1000} caption="Drivers">
                  {filteredDrivers.map((driver, index) => (
                    <tr key={driver.employee_id ?? index}>
                      <td>
                        <div className="flex items-center gap-3">
                          <Avatar text={initials(driver.name)} className="size-10" tone={String(driver.availability_status).toUpperCase() === 'AVAILABLE' ? 'lime' : 'cream'} />
                          <div>
                            <p className="font-semibold text-ink">{driver.name ?? '—'}</p>
                            <p className="font-mono text-xs text-stone">EMP #{driver.employee_id ?? '—'}</p>
                          </div>
                        </div>
                      </td>
                      <td>{driver.phone ?? '—'}</td>
                      <td>{formatLabel(driver.department)}</td>
                      <td className="font-mono text-xs">{driver.license_no ?? '—'}</td>
                      <td><LicenceExpiry value={driver.license_expiry} /></td>
                      <td><StatusBadge status={driver.availability_status} /></td>
                      <td><StatusBadge status={driver.employment_status} /></td>
                    </tr>
                  ))}
                </DataTable>
              )}
      </Panel>
    </div>
  )
}

export default Drivers
