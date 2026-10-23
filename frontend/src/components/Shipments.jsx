import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError, apiGet } from '../services/apiClient.js'
import { formatDate, formatLabel } from '../lib/format.js'
import { StageStrip } from './charts.jsx'
import OperationsShipments from './OperationsShipments.jsx'
import { DataTable, EmptyState, ErrorState, FilterChips, IdTag, PageHeader, Panel, RefreshButton, SearchField, SkeletonRows, StatTile, StatusBadge, stagger } from './ui.jsx'

const STAGES = ['CREATED', 'PICKED_UP', 'IN_TRANSIT', 'OUT_FOR_DELIVERY', 'DELIVERED', 'CANCELLED']

function Shipments(props) {
  const roleId = Number(props.session.user.roleId)
  // Staff get the server-driven desk; drivers and customers keep the scoped list.
  return roleId === 1 || roleId === 2 ? <OperationsShipments {...props} /> : <ScopedShipments {...props} />
}

function ScopedShipments({ session, onAuthExpired, onNavigate }) {
  const [shipments, setShipments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('ALL')
  const [refreshKey, setRefreshKey] = useState(0)

  const loadShipments = useCallback(async () => {
    setLoading(true)
    setError('')

    try {
      const data = await apiGet('/shipments', session.accessToken)

      if (!Array.isArray(data)) {
        throw new Error('Unexpected response from the shipments API.')
      }

      setShipments(data)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onAuthExpired()
        return
      }

      setError(err.message || 'Unable to load shipments.')
    } finally {
      setLoading(false)
    }
  }, [session.accessToken, onAuthExpired])

  useEffect(() => {
    loadShipments()
  }, [loadShipments, refreshKey])

  const filteredShipments = useMemo(() => {
    const query = search.trim().toLowerCase()

    return shipments.filter((shipment) => {
      if (statusFilter !== 'ALL' && String(shipment.shipment_status ?? '').toUpperCase() !== statusFilter) return false
      if (!query) return true
      return String(shipment.shipment_id ?? '').toLowerCase().includes(query) ||
        String(shipment.order_id ?? '').toLowerCase().includes(query) ||
        String(shipment.shipment_status ?? '').toLowerCase().includes(query)
    })
  }, [shipments, search, statusFilter])

  const activeCount = shipments.filter((shipment) =>
    !['DELIVERED', 'CANCELLED'].includes(String(shipment.shipment_status ?? '').toUpperCase())
  ).length

  const deliveredCount = shipments.filter(
    (shipment) => String(shipment.shipment_status ?? '').toUpperCase() === 'DELIVERED'
  ).length

  const counts = shipments.reduce((result, shipment) => {
    const key = String(shipment.shipment_status ?? '').toUpperCase()
    return { ...result, [key]: (result[key] ?? 0) + 1 }
  }, {})
  const stages = STAGES.map((status) => ({ key: status, label: formatLabel(status), value: counts[status] ?? 0 }))
  const options = [{ value: 'ALL', label: 'All', count: shipments.length }, ...STAGES.filter((status) => counts[status]).map((status) => ({ value: status, label: formatLabel(status), count: counts[status] }))]

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Shipment management"
        title="Shipments"
        accent="in flight."
        description="Monitor shipment status and delivery progress across the network."
        actions={<RefreshButton onClick={() => setRefreshKey((key) => key + 1)} loading={loading} label="Refresh shipments" />}
      />

      <div className="grid gap-4 lg:grid-cols-[1fr_1fr_1fr_1.6fr]">
        <StatTile label="Total shipments" value={shipments.length} icon="route" loading={loading && !shipments.length} />
        <StatTile label="Active" value={activeCount} hint="Not delivered or cancelled" icon="truck" tone="lime" loading={loading && !shipments.length} style={stagger(1)} />
        <StatTile label="Delivered" value={deliveredCount} icon="check" tone="ink" loading={loading && !shipments.length} style={stagger(2)} />
        <Panel eyebrow="Distribution" title="By stage" style={stagger(3)}>
          {shipments.length ? <StageStrip items={stages} /> : <p className="text-sm text-stone">{loading ? 'Loading…' : 'No shipments yet.'}</p>}
        </Panel>
      </div>

      <Panel
        bodyClassName="p-0"
        title="All shipments"
        subtitle={`${filteredShipments.length} of ${shipments.length} shipments`}
        actions={<SearchField value={search} onChange={setSearch} placeholder="Shipment, order or status…" label="Search shipments" className="w-full sm:w-72" />}
      >
        <div className="border-b border-line px-5 py-3 sm:px-6">
          <FilterChips label="Filter shipments by status" options={options} value={statusFilter} onChange={setStatusFilter} />
        </div>
        {loading && shipments.length === 0 ? (
          <SkeletonRows rows={4} label="Loading shipments" />
        ) : error ? (
          <ErrorState title="Unable to load shipments" message={error} onRetry={() => setRefreshKey((key) => key + 1)} />
        ) : filteredShipments.length === 0 ? (
          <EmptyState
            icon="route"
            title={search || statusFilter !== 'ALL' ? 'No matching shipments' : 'No shipments yet'}
            text={search || statusFilter !== 'ALL' ? 'Try another shipment ID, order ID or status.' : 'Shipments will appear here when they are available.'}
            action={(search || statusFilter !== 'ALL') && <button type="button" onClick={() => { setSearch(''); setStatusFilter('ALL') }} className="btn btn-ink">Clear filters</button>}
          />
        ) : (
          <DataTable head={['Shipment', 'Order', 'Origin', 'Route', 'Shipped', 'Estimated delivery', 'Status']} minWidth={860} caption="Shipments">
            {filteredShipments.map((shipment, index) => (
              <tr key={shipment.shipment_id ?? index}>
                <td><IdTag>{shipment.shipment_id}</IdTag></td>
                <td>#{shipment.order_id ?? '—'}</td>
                <td>{shipment.warehouse_id ? `Warehouse ${shipment.warehouse_id}` : '—'}</td>
                <td>{shipment.route_id ? `Route ${shipment.route_id}` : '—'}</td>
                <td>{formatDate(shipment.shipment_date)}</td>
                <td>{formatDate(shipment.actual_delivery ?? shipment.estimated_delivery)}</td>
                <td><StatusBadge status={shipment.shipment_status} /></td>
              </tr>
            ))}
          </DataTable>
        )}
      </Panel>
      {onNavigate && shipments.length > 0 && (
        <p className="text-sm text-stone">Need the event history? <button type="button" onClick={() => onNavigate('tracking')} className="font-semibold text-ink underline decoration-lime decoration-2 underline-offset-4">Open tracking</button></p>
      )}
    </div>
  )
}

export default Shipments
