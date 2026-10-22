import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError, apiGet } from '../services/apiClient.js'
import { formatDate, formatLabel } from '../lib/format.js'
import { EmptyState, ErrorState, Icon, Notice, PageHeader, RefreshButton, SearchField, StatTile, StatusBadge, stagger } from './ui.jsx'

function formatCapacity(value) {
  const capacity = Number(value)
  return Number.isFinite(capacity) ? `${capacity.toLocaleString('en-IN')} kg` : '—'
}

function Vehicles({ session, onAuthExpired }) {
  const [vehicles, setVehicles] = useState([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')

  const loadVehicles = useCallback(async (isRefresh = false) => {
    isRefresh ? setRefreshing(true) : setLoading(true)
    setError('')
    try {
      const data = await apiGet('/vehicles', session.accessToken)
      if (!Array.isArray(data)) throw new Error('Unexpected response from the vehicles API.')
      setVehicles(data)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onAuthExpired()
        return
      }
      setError(err instanceof ApiError && err.status === 403 ? 'You do not have permission to view vehicles.' : err.message || 'Unable to load vehicles.')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [session.accessToken, onAuthExpired])

  useEffect(() => { loadVehicles() }, [loadVehicles])

  const filteredVehicles = useMemo(() => {
    const query = search.trim().toLowerCase()
    if (!query) return vehicles
    return vehicles.filter((vehicle) => [vehicle.vehicle_id, vehicle.registration_no, vehicle.vehicle_type, vehicle.fuel_type, vehicle.status].some((value) => String(value ?? '').toLowerCase().includes(query)))
  }, [vehicles, search])

  const activeCount = vehicles.filter((vehicle) => ['ACTIVE', 'AVAILABLE'].includes(String(vehicle.status ?? '').toUpperCase())).length
  const maintenanceCount = vehicles.filter((vehicle) => ['MAINTENANCE', 'SERVICE'].some((status) => String(vehicle.status ?? '').toUpperCase().includes(status))).length
  const totalCapacity = vehicles.reduce((sum, vehicle) => sum + (Number(vehicle.capacity) || 0), 0)

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Fleet management"
        title="The fleet,"
        accent="road-ready."
        description="Review current fleet capacity, fuel type, and availability."
        actions={<RefreshButton onClick={() => loadVehicles(true)} loading={loading || refreshing} label="Refresh vehicles" />}
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile label="Total vehicles" value={loading ? '—' : vehicles.length} icon="vehicle" loading={loading} />
        <StatTile label="In service" value={loading ? '—' : activeCount} hint="Active or available" icon="check" tone="lime" loading={loading} style={stagger(1)} />
        <StatTile label="In maintenance" value={loading ? '—' : maintenanceCount} hint="Maintenance or service" icon="alert" tone="cream" loading={loading} style={stagger(2)} />
        <StatTile label="Total capacity" value={loading ? '—' : formatCapacity(totalCapacity)} icon="weight" tone="ink" loading={loading} style={stagger(3)} />
      </div>

      {error && <Notice tone="error" onRetry={() => loadVehicles()}>{error}</Notice>}

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-stone" aria-live="polite">{loading ? 'Loading vehicle records…' : `${filteredVehicles.length} record${filteredVehicles.length === 1 ? '' : 's'} found`}</p>
        <SearchField value={search} onChange={setSearch} placeholder="Registration, type, fuel or status…" label="Search vehicles" className="sm:w-80" />
      </div>

      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{[1, 2, 3].map((item) => <div key={item} className="skeleton h-56 rounded-[1.5rem]!" />)}</div>
      ) : error ? (
        <div className="panel"><ErrorState title="Vehicle records could not be loaded" message="Resolve the error above and try again." /></div>
      ) : filteredVehicles.length === 0 ? (
        <div className="panel"><EmptyState icon="vehicle" title={search ? 'No matching vehicles' : 'No vehicles yet'} text={search ? 'Try a registration number, type, fuel type, or status.' : 'Vehicle records will appear here when available.'} /></div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {filteredVehicles.map((vehicle, index) => (
            <article key={vehicle.vehicle_id ?? index} className="panel animate-rise group p-5 transition hover:-translate-y-0.5 hover:shadow-[var(--shadow-lift)]" style={stagger(Math.min(index, 8), 50)}>
              <div className="flex items-start justify-between gap-3">
                <div className="inline-flex items-stretch overflow-hidden rounded-lg border-2 border-ink font-mono text-lg font-bold tracking-wider">
                  <span className="w-2.5 bg-lime" aria-hidden="true" />
                  <span className="bg-paper px-3 py-1.5">{vehicle.registration_no ?? '—'}</span>
                </div>
                <StatusBadge status={vehicle.status} />
              </div>
              <div className="mt-6 flex items-end justify-between gap-4">
                <div>
                  <p className="eyebrow text-stone">Vehicle #{vehicle.vehicle_id ?? '—'}</p>
                  <p className="font-display mt-1 text-2xl font-semibold">{formatLabel(vehicle.vehicle_type)}</p>
                </div>
                <span className="grid size-12 place-items-center rounded-2xl bg-ink text-lime transition group-hover:rotate-[-6deg]"><Icon name="vehicle" className="size-6" /></span>
              </div>
              <dl className="mt-5 grid grid-cols-3 gap-3 border-t border-line pt-4 text-sm">
                <div><dt className="eyebrow text-mist">Capacity</dt><dd className="mt-1 font-semibold">{formatCapacity(vehicle.capacity)}</dd></div>
                <div><dt className="eyebrow text-mist">Fuel</dt><dd className="mt-1 font-semibold">{formatLabel(vehicle.fuel_type)}</dd></div>
                <div><dt className="eyebrow text-mist">Purchased</dt><dd className="mt-1 font-semibold">{formatDate(vehicle.purchase_date)}</dd></div>
              </dl>
            </article>
          ))}
        </div>
      )}
    </div>
  )
}

export default Vehicles
