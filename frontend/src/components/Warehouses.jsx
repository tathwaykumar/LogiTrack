import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError, apiGet } from '../services/apiClient.js'
import { formatDate, formatNumber } from '../lib/format.js'
import { Meter } from './charts.jsx'
import { DataTable, EmptyState, ErrorState, FilterChips, Icon, PageHeader, Panel, RefreshButton, SearchField, SkeletonRows, StatTile, StatusBadge, stagger } from './ui.jsx'

function Warehouses({ session, onAuthExpired, onNavigate }) {
  const [warehouses, setWarehouses] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('ALL')
  const [openId, setOpenId] = useState(null)
  const [stockWarehouse, setStockWarehouse] = useState('ALL')
  const [stockStatus, setStockStatus] = useState('ALL')
  const [stockSearch, setStockSearch] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await apiGet('/operations/warehouses', session.accessToken)
      if (!Array.isArray(data)) throw new Error('Unexpected response from the warehouses API.')
      setWarehouses(data)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onAuthExpired()
        return
      }
      setError(err instanceof ApiError && err.status === 403 ? 'You do not have permission to view warehouses.' : err.message || 'Unable to load warehouses.')
    } finally {
      setLoading(false)
    }
  }, [session.accessToken, onAuthExpired])

  useEffect(() => { load() }, [load, refreshKey])

  const visible = useMemo(() => {
    const query = search.trim().toLowerCase()
    return warehouses.filter((w) => {
      if (filter === 'ACTIVE' && !w.is_active) return false
      if (filter === 'INACTIVE' && w.is_active) return false
      if (filter === 'LOW' && w.low_stock_lines === 0) return false
      if (filter === 'GAPS' && w.data_gaps.length === 0) return false
      return !query || [w.warehouse_name, w.city, w.address, w.manager_name].some((value) => String(value ?? '').toLowerCase().includes(query))
    })
  }, [warehouses, search, filter])

  // One row per stocked product per warehouse. Available = what can still be promised; on hand adds the
  // units reserved for open orders. Low stock means available is at or below that line's reorder level.
  const stockLines = useMemo(() => warehouses.flatMap((w) => w.inventory.map((line) => ({
    ...line, warehouse_id: w.warehouse_id, warehouse_name: w.warehouse_name, city: w.city,
    state: line.out_of_stock ? 'OUT' : line.low_stock ? 'LOW' : 'IN',
  }))), [warehouses])
  const visibleStock = useMemo(() => {
    const query = stockSearch.trim().toLowerCase()
    return stockLines.filter((line) => (
      (stockWarehouse === 'ALL' || String(line.warehouse_id) === stockWarehouse) &&
      (stockStatus === 'ALL' || line.state === stockStatus) &&
      (!query || String(line.product_name ?? '').toLowerCase().includes(query) || String(line.product_id).includes(query))
    ))
  }, [stockLines, stockWarehouse, stockStatus, stockSearch])
  const stockCounts = stockLines.reduce((counts, line) => ({ ...counts, [line.state]: (counts[line.state] ?? 0) + 1 }), {})

  const totals = warehouses.reduce((sum, w) => ({
    onHand: sum.onHand + w.units_on_hand, reserved: sum.reserved + w.units_reserved, low: sum.low + w.low_stock_lines,
    orders: sum.orders + w.orders_in_fulfilment.count,
  }), { onHand: 0, reserved: 0, low: 0, orders: 0 })

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Warehouse network"
        title="Every warehouse,"
        accent="at a glance."
        description="Stock, reservations, capacity and the orders each warehouse is fulfilling, straight from the database. Nothing here is estimated."
        actions={<RefreshButton onClick={() => setRefreshKey((key) => key + 1)} loading={loading} label="Refresh warehouses" />}
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile label="Warehouses" value={loading ? '—' : warehouses.length} hint={`${warehouses.filter((w) => w.is_active).length} active`} icon="building" loading={loading && !warehouses.length} />
        <StatTile label="Units on hand" value={loading ? '—' : formatNumber(totals.onHand)} hint={`${formatNumber(totals.reserved)} reserved for open orders`} icon="box" tone="lime" loading={loading && !warehouses.length} style={stagger(1)} />
        <StatTile label="Low-stock lines" value={loading ? '—' : totals.low} hint="At or below reorder level" icon="alert" tone="cream" loading={loading && !warehouses.length} style={stagger(2)} />
        <StatTile label="Orders in fulfilment" value={loading ? '—' : totals.orders} hint="Planned or in transit" icon="route" tone="ink" loading={loading && !warehouses.length} style={stagger(3)} />
      </div>

      {!loading && !error && warehouses.length > 0 && (
        <Panel
          bodyClassName="p-0"
          eyebrow="Inventory"
          title="Stock across the network"
          subtitle={`${visibleStock.length} of ${stockLines.length} stock lines`}
          actions={<SearchField value={stockSearch} onChange={setStockSearch} placeholder="Product name or ID…" label="Search inventory" className="w-full sm:w-72" />}
        >
          <div className="flex flex-col gap-3 border-b border-line px-5 py-3 sm:px-6 lg:flex-row lg:items-center lg:justify-between">
            <label className="inline-flex items-center gap-2 text-sm text-stone">Warehouse
              <select className="field py-1.5!" value={stockWarehouse} onChange={(event) => setStockWarehouse(event.target.value)} aria-label="Filter inventory by warehouse">
                <option value="ALL">All warehouses</option>
                {warehouses.map((w) => <option key={w.warehouse_id} value={w.warehouse_id}>{w.warehouse_name} ({w.inventory.length} products)</option>)}
              </select>
            </label>
            <FilterChips
              label="Filter inventory by stock status"
              value={stockStatus}
              onChange={setStockStatus}
              options={[
                { value: 'ALL', label: 'All', count: stockLines.length },
                { value: 'IN', label: 'In stock', count: stockCounts.IN ?? 0 },
                { value: 'LOW', label: 'Low stock', count: stockCounts.LOW ?? 0 },
                { value: 'OUT', label: 'Out of stock', count: stockCounts.OUT ?? 0 },
              ]}
            />
          </div>
          {visibleStock.length === 0 ? (
            <EmptyState icon="box" title={stockLines.length ? 'No stock line matches' : 'No inventory recorded'} text={stockLines.length ? 'Try a different warehouse, status or search.' : 'No warehouse has stock recorded yet.'} action={stockLines.length > 0 && <button type="button" className="btn btn-ink" onClick={() => { setStockWarehouse('ALL'); setStockStatus('ALL'); setStockSearch('') }}>Clear filters</button>} />
          ) : (
            <DataTable head={['Warehouse', 'Product', 'Product ID', 'On hand', 'Reserved', 'Available', 'Reorder at', 'Status']} minWidth={860} caption="Inventory by warehouse and product">
              {visibleStock.map((line) => (
                <tr key={`${line.warehouse_id}-${line.product_id}`}>
                  <td><span className="block font-medium">{line.warehouse_name}</span><span className="block text-xs text-stone">{line.city}</span></td>
                  <td className="font-medium text-ink">{line.product_name ?? `Product #${line.product_id}`}</td>
                  <td className="font-mono text-xs">{line.product_id}</td>
                  <td className="tabular-nums">{formatNumber(line.on_hand)}</td>
                  <td className="tabular-nums">{formatNumber(line.reserved)}</td>
                  <td className="font-semibold tabular-nums">{formatNumber(line.available)}</td>
                  <td className="tabular-nums">{formatNumber(line.reorder_level)}</td>
                  <td>{line.state === 'OUT' ? <StatusBadge status="FAILED" label="Out of stock" /> : line.state === 'LOW' ? <StatusBadge status="PENDING" label="Low stock" /> : <StatusBadge status="ACTIVE" label="In stock" />}</td>
                </tr>
              ))}
            </DataTable>
          )}
          <p className="border-t border-line px-5 py-3 text-xs text-mist sm:px-6">
            Available is what can still be promised to new orders; reserved units are held for open orders; on hand is the two together.
            Low stock means available is at or below that line's reorder level. Products have no separate SKU in the database, so the product ID identifies them.
          </p>
        </Panel>
      )}

      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <FilterChips
          label="Filter warehouses"
          value={filter}
          onChange={setFilter}
          options={[
            { value: 'ALL', label: 'All', count: warehouses.length },
            { value: 'ACTIVE', label: 'Active', count: warehouses.filter((w) => w.is_active).length },
            { value: 'INACTIVE', label: 'Not active', count: warehouses.filter((w) => !w.is_active).length },
            { value: 'LOW', label: 'Low stock', count: warehouses.filter((w) => w.low_stock_lines > 0).length },
            { value: 'GAPS', label: 'Data gaps', count: warehouses.filter((w) => w.data_gaps.length > 0).length },
          ]}
        />
        <SearchField value={search} onChange={setSearch} placeholder="Name, city, address or manager…" label="Search warehouses" className="lg:w-80" />
      </div>

      {loading && warehouses.length === 0 ? (
        <div className="panel"><SkeletonRows rows={3} height="h-32" label="Loading warehouses" /></div>
      ) : error ? (
        <div className="panel"><ErrorState title="Unable to load warehouses" message={error} onRetry={() => setRefreshKey((key) => key + 1)} /></div>
      ) : visible.length === 0 ? (
        <div className="panel"><EmptyState icon="building" title={warehouses.length ? 'No warehouse matches' : 'No warehouses yet'} text={warehouses.length ? 'Try a different search or filter.' : 'Warehouses will appear here once they are created.'} action={warehouses.length > 0 && <button type="button" className="btn btn-ink" onClick={() => { setSearch(''); setFilter('ALL') }}>Clear filters</button>} /></div>
      ) : (
        <div className="space-y-5">
          {visible.map((w, index) => (
            <WarehouseCard key={w.warehouse_id} warehouse={w} index={index} open={openId === w.warehouse_id} onToggle={() => setOpenId(openId === w.warehouse_id ? null : w.warehouse_id)} onNavigate={onNavigate} />
          ))}
        </div>
      )}
    </div>
  )
}

function WarehouseCard({ warehouse: w, index, open, onToggle, onNavigate }) {
  const shipments = w.outgoing_shipments
  return (
    <article className="panel animate-rise overflow-hidden" style={stagger(Math.min(index, 6), 50)}>
      <div className="grid gap-6 p-5 sm:p-6 lg:grid-cols-[1.2fr_1fr_1fr]">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <p className="eyebrow text-stone">Warehouse #{w.warehouse_id}</p>
            <StatusBadge status={w.status} label={w.status ?? 'Unknown'} />
          </div>
          <h2 className="font-display mt-2 text-2xl font-semibold">{w.warehouse_name}</h2>
          <p className="mt-1 flex items-start gap-2 text-sm text-stone"><Icon name="pin" className="mt-0.5 size-4" />{w.address}, {w.city}</p>
          <p className="mt-1 text-sm text-stone">Manager: {w.manager_name ?? 'not assigned'}</p>
          <p className="mt-1 text-sm text-stone">{w.inventory.length} distinct product{w.inventory.length === 1 ? '' : 's'} stocked</p>
        </div>

        <div>
          <p className="eyebrow text-stone">Stock</p>
          <dl className="mt-3 grid grid-cols-3 gap-3">
            <div><dt className="text-xs text-stone">Available</dt><dd className="mt-1 text-2xl font-semibold tabular-nums">{formatNumber(w.units_available)}</dd></div>
            <div><dt className="text-xs text-stone">Reserved</dt><dd className="mt-1 text-2xl font-semibold tabular-nums">{formatNumber(w.units_reserved)}</dd></div>
            <div><dt className="text-xs text-stone">On hand</dt><dd className="mt-1 text-2xl font-semibold tabular-nums">{formatNumber(w.units_on_hand)}</dd></div>
          </dl>
          <div className="mt-4">
            {w.utilisation_percent !== null ? (
              <>
                <Meter label="Capacity used" value={w.utilisation_percent} detail={`${formatNumber(w.units_on_hand)} of ${formatNumber(w.capacity)} (${w.utilisation_basis})`} />
              </>
            ) : <p className="text-sm text-stone">Capacity utilisation is unavailable: no capacity is recorded.</p>}
          </div>
        </div>

        <div>
          <p className="eyebrow text-stone">Shipments from here</p>
          <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
            <div><dt className="text-xs text-stone">Awaiting pickup</dt><dd className="mt-1 text-xl font-semibold tabular-nums">{shipments.awaiting_pickup}</dd></div>
            <div><dt className="text-xs text-stone">In flight</dt><dd className="mt-1 text-xl font-semibold tabular-nums">{shipments.in_flight}</dd></div>
            <div><dt className="text-xs text-stone">Delivered</dt><dd className="mt-1 text-xl font-semibold tabular-nums">{shipments.delivered}</dd></div>
            <div><dt className="text-xs text-stone">Active routes out</dt><dd className="mt-1 text-xl font-semibold tabular-nums">{w.outgoing_routes}</dd></div>
          </dl>
          <p className="mt-3 text-xs text-mist">Incoming: {w.incoming_shipments.note}</p>
        </div>
      </div>

      {w.data_gaps.length > 0 && (
        <ul className="border-t border-line bg-warn-soft/50 px-5 py-3 text-sm text-warn sm:px-6">
          {w.data_gaps.map((gap) => <li key={gap} className="flex items-start gap-2"><Icon name="alert" className="mt-0.5 size-4" />{gap}</li>)}
        </ul>
      )}

      <button type="button" onClick={onToggle} aria-expanded={open} className="flex w-full items-center justify-between border-t border-line px-5 py-3 text-left text-sm font-semibold hover:bg-cream/50 sm:px-6">
        <span>{open ? 'Hide' : 'Show'} inventory and orders ({w.inventory.length} products · {w.orders_in_fulfilment.count} orders)</span>
        <Icon name="arrowRight" className={`size-4 transition-transform ${open ? '-rotate-90' : 'rotate-90'}`} />
      </button>

      {open && (
        <div className="space-y-6 border-t border-line bg-ivory/60 p-5 sm:p-6">
          {w.inventory.length === 0 ? <p className="text-sm text-stone">No inventory is recorded for this warehouse.</p> : (
            <div className="overflow-hidden rounded-2xl border border-line bg-paper">
              <DataTable head={['Product', 'Available', 'Reserved', 'On hand', 'Reorder at', 'Updated', 'Flags']} minWidth={720} caption={`Inventory at ${w.warehouse_name}`}>
                {w.inventory.map((line) => (
                  <tr key={line.product_id}>
                    <td className="font-medium text-ink">{line.product_name ?? `Product #${line.product_id}`}</td>
                    <td className="tabular-nums">{formatNumber(line.available)}</td>
                    <td className="tabular-nums">{formatNumber(line.reserved)}</td>
                    <td className="tabular-nums">{formatNumber(line.on_hand)}</td>
                    <td className="tabular-nums">{formatNumber(line.reorder_level)}</td>
                    <td>{formatDate(line.last_updated)}</td>
                    <td>{line.out_of_stock ? <StatusBadge status="FAILED" label="Out of stock" /> : line.low_stock ? <StatusBadge status="PENDING" label="Low stock" /> : <span className="text-mist">—</span>}</td>
                  </tr>
                ))}
              </DataTable>
            </div>
          )}

          <div>
            <h3 className="eyebrow text-stone">Orders being fulfilled from here</h3>
            {w.orders_in_fulfilment.orders.length === 0 ? <p className="mt-2 text-sm text-stone">No open orders are planned or shipping from this warehouse.</p> : (
              <ul className="mt-3 grid gap-2 sm:grid-cols-2">
                {w.orders_in_fulfilment.orders.map((order) => (
                  <li key={order.order_id} className="flex items-center justify-between gap-3 rounded-2xl border border-line bg-paper px-4 py-3 text-sm">
                    <span><span className="font-semibold">Order #{order.order_id}</span> <span className="text-stone">· {order.customer_name}</span>
                      <span className="block text-xs text-stone">{order.shipment_id ? `Shipment #${order.shipment_id} · ${order.shipment_status}` : `Plan: ${order.fulfilment_status ?? 'none'}`}</span></span>
                    <StatusBadge status={order.order_status} />
                  </li>
                ))}
              </ul>
            )}
            {w.orders_in_fulfilment.count > w.orders_in_fulfilment.orders.length && <p className="mt-2 text-xs text-mist">Showing {w.orders_in_fulfilment.orders.length} of {w.orders_in_fulfilment.count}. {onNavigate && <button type="button" className="font-semibold underline" onClick={() => onNavigate('shipments')}>Open the shipment desk</button>}</p>}
          </div>
        </div>
      )}
    </article>
  )
}

export default Warehouses
