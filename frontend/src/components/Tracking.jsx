import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError, apiGet, apiPost } from '../services/apiClient.js'
import { formatDate, formatDateTime, formatLabel } from '../lib/format.js'
import { nextShipmentStatuses } from '../lib/status.js'
import { EmptyState, ErrorState, Icon, Notice, PageHeader, Panel, RefreshButton, SearchField } from './ui.jsx'

const PROGRESS_STAGES = ['CREATED', 'PICKED_UP', 'IN_TRANSIT', 'OUT_FOR_DELIVERY', 'DELIVERED']
const STAGE_ICONS = { CREATED: 'box', PICKED_UP: 'warehouse', IN_TRANSIT: 'route', OUT_FOR_DELIVERY: 'truck', DELIVERED: 'check' }

function Tracking({ session, onAuthExpired }) {
  const [shipments, setShipments] = useState([])
  const [selectedId, setSelectedId] = useState('')
  const [events, setEvents] = useState([])
  const [loadingShipments, setLoadingShipments] = useState(true)
  const [loadingTimeline, setLoadingTimeline] = useState(false)
  const [error, setError] = useState('')
  const [timelineError, setTimelineError] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)
  const [status, setStatus] = useState('IN_TRANSIT')
  const [location, setLocation] = useState('')
  const [remarks, setRemarks] = useState('')
  const [updating, setUpdating] = useState(false)
  const [updateError, setUpdateError] = useState('')
  const [updateSuccess, setUpdateSuccess] = useState('')
  const [search, setSearch] = useState('')
  const canUpdateTracking = [1, 2, 3].includes(Number(session.user.roleId))

  const loadShipments = useCallback(async () => {
    setLoadingShipments(true)
    setError('')

    try {
      const data = await apiGet('/shipments', session.accessToken)

      if (!Array.isArray(data)) {
        throw new Error('Unexpected response from the shipments API.')
      }

      setShipments(data)
      setSelectedId((current) =>
        data.some((item) => String(item.shipment_id) === current)
          ? current
          : String(data[0]?.shipment_id ?? '')
      )
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onAuthExpired()
        return
      }

      setError(err.message || 'Unable to load shipments.')
      setShipments([])
      setSelectedId('')
    } finally {
      setLoadingShipments(false)
    }
  }, [session.accessToken, onAuthExpired])

  useEffect(() => {
    loadShipments()
  }, [loadShipments, refreshKey])

  useEffect(() => {
    if (!selectedId) {
      setEvents([])
      setTimelineError('')
      setLoadingTimeline(false)
      return
    }

    let active = true

    async function loadTimeline() {
      setLoadingTimeline(true)
      setTimelineError('')
      setEvents([])

      try {
        const data = await apiGet(`/shipments/${selectedId}/timeline`, session.accessToken)

        if (active) {
          // The API returns { ..., tracking_events: [...] }.
          const timeline = Array.isArray(data)
            ? data
            : data.tracking_events ?? data.timeline ?? data.tracking ?? data.events ?? []

          if (!Array.isArray(timeline)) {
            throw new Error('Unexpected tracking timeline response.')
          }

          setEvents(timeline)
        }
      } catch (err) {
        if (!active) return

        if (err instanceof ApiError && err.status === 401) {
          onAuthExpired()
          return
        }

        setTimelineError(err.message || 'Unable to load this shipment timeline.')
      } finally {
        if (active) setLoadingTimeline(false)
      }
    }

    loadTimeline()

    return () => {
      active = false
    }
  }, [selectedId, session.accessToken, onAuthExpired])

  const selectedShipment = shipments.find((item) => String(item.shipment_id) === selectedId)
  const filteredShipments = useMemo(() => {
    const query = search.trim().toLowerCase()
    if (!query) return shipments
    return shipments.filter((item) => [item.shipment_id, item.order_id, item.shipment_status].some((value) => String(value ?? '').toLowerCase().includes(query)))
  }, [shipments, search])
  // Newest first in insertion order: the order in which the database applied each event's
  // status, so the "Latest" event always matches the shipment's current status.
  const orderedEvents = useMemo(() => [...events].sort((a, b) => (Number(b.tracking_id) || 0) - (Number(a.tracking_id) || 0)), [events])
  const statusOptions = nextShipmentStatuses(selectedShipment?.shipment_status)

  function selectShipment(id) {
    setSelectedId(id)
    setUpdateError('')
    setUpdateSuccess('')
  }

  async function submitTrackingUpdate(event) {
    event.preventDefault()
    if (!selectedId) return
    setUpdating(true)
    setUpdateError('')
    setUpdateSuccess('')

    try {
      const data = await apiPost('/tracking', {
        shipment_id: Number(selectedId),
        status: statusOptions.includes(status) ? status : statusOptions[0],
        location: location.trim() || null,
        remarks: remarks.trim() || null,
      }, session.accessToken)
      setShipments((current) => current.map((shipment) => String(shipment.shipment_id) === selectedId ? { ...shipment, shipment_status: data.shipment_status ?? data.status } : shipment))
      setEvents((current) => [...current, {
        tracking_id: data.tracking_id,
        status: data.status,
        location: data.location,
        remarks: data.remarks,
        tracking_timestamp: data.tracking_timestamp,
      }])
      setLocation('')
      setRemarks('')
      setUpdateSuccess('Tracking status updated successfully.')
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onAuthExpired()
        return
      }
      setUpdateError(err.message || 'Unable to update tracking status.')
    } finally {
      setUpdating(false)
    }
  }

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Shipment visibility"
        title="Every milestone,"
        accent="in order."
        description="Follow a shipment from warehouse to doorstep with its full tracking history."
        actions={<RefreshButton onClick={() => setRefreshKey((key) => key + 1)} loading={loadingShipments} label="Refresh tracking" />}
      />

      <div className="grid gap-6 xl:grid-cols-[22rem_minmax(0,1fr)]">
        <Panel eyebrow="Shipments" title={loadingShipments ? 'Loading…' : `${shipments.length} on record`} bodyClassName="p-0" className="xl:sticky xl:top-24 xl:self-start">
          <div className="border-b border-line p-4">
            <SearchField value={search} onChange={setSearch} placeholder="Shipment, order or status" label="Search shipments" />
          </div>
          {loadingShipments ? (
            <div className="space-y-2 p-4">{[1, 2, 3, 4].map((item) => <div key={item} className="skeleton h-16" />)}</div>
          ) : error ? (
            <ErrorState title="Shipments unavailable" message={error} onRetry={() => setRefreshKey((key) => key + 1)} />
          ) : shipments.length === 0 ? (
            <EmptyState icon="route" title="No shipments yet" text="Tracking history will appear here when you have a shipment." />
          ) : (
            <ul className="scrollbar-thin max-h-[32rem] space-y-1 overflow-y-auto p-2" aria-label="Select shipment">
              {filteredShipments.map((shipment) => {
                const active = String(shipment.shipment_id) === selectedId
                return (
                  <li key={shipment.shipment_id}>
                    <button
                      type="button"
                      aria-pressed={active}
                      onClick={() => selectShipment(String(shipment.shipment_id))}
                      className={`flex w-full items-center gap-3 rounded-2xl px-3 py-3 text-left transition-colors ${active ? 'bg-ink text-paper' : 'hover:bg-cream'}`}
                    >
                      <span className={`grid size-10 shrink-0 place-items-center rounded-full ${active ? 'bg-lime text-ink' : 'bg-cream text-ink'}`}>
                        <Icon name={STAGE_ICONS[shipment.shipment_status] ?? 'box'} className="size-4" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block font-semibold">Shipment #{shipment.shipment_id}</span>
                        <span className={`block truncate text-xs ${active ? 'text-paper/60' : 'text-stone'}`}>Order #{shipment.order_id ?? '—'} · {formatLabel(shipment.shipment_status, 'Unknown status')}</span>
                      </span>
                      {active && <Icon name="arrowRight" className="size-4 text-lime" />}
                    </button>
                  </li>
                )
              })}
              {filteredShipments.length === 0 && <li className="px-3 py-8 text-center text-sm text-stone">No shipment matches “{search}”.</li>}
            </ul>
          )}
        </Panel>

        <div className="min-w-0 space-y-6">
          {selectedShipment ? (
            <ShipmentHero shipment={selectedShipment} />
          ) : !loadingShipments && !error && shipments.length > 0 ? (
            <div className="panel"><EmptyState icon="pin" title="Select a shipment" text="Choose a shipment to see its progress." /></div>
          ) : null}

          {selectedShipment && (
            <div className="grid gap-6 2xl:grid-cols-[minmax(0,1fr)_22rem]">
              <Panel eyebrow="History" title="Tracking timeline" subtitle="Most recent event first">
                {loadingTimeline ? (
                  <div className="space-y-4">{[1, 2, 3].map((item) => <div key={item} className="skeleton h-20" />)}</div>
                ) : timelineError ? (
                  <ErrorState title="Unable to load tracking history" message={timelineError} onRetry={() => setRefreshKey((key) => key + 1)} />
                ) : orderedEvents.length === 0 ? (
                  <EmptyState icon="clock" title="No events yet" text="No tracking events have been recorded for this shipment yet." />
                ) : (
                  <ol className="relative">
                    {orderedEvents.map((event, index) => (
                      <li key={event.tracking_id ?? event.id ?? index} className="relative flex gap-4 pb-6 last:pb-0">
                        {index !== orderedEvents.length - 1 && <span className="absolute top-10 bottom-0 left-5 w-px bg-line" aria-hidden="true" />}
                        <span className={`relative z-10 grid size-10 shrink-0 place-items-center rounded-full ${index === 0 ? 'bg-lime text-ink ring-4 ring-lime/30' : 'bg-cream text-graphite'}`}>
                          <Icon name={STAGE_ICONS[event.status] ?? (event.status === 'CANCELLED' ? 'x' : 'pin')} className="size-4" />
                        </span>
                        <div className={`min-w-0 flex-1 rounded-2xl border p-4 ${index === 0 ? 'border-ink bg-paper' : 'border-line bg-ivory/50'}`}>
                          <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-start">
                            <div>
                              <div className="flex flex-wrap items-center gap-2">
                                <p className="font-display text-lg font-semibold">{formatLabel(event.status ?? event.tracking_status, 'Update')}</p>
                                {index === 0 && <span className="eyebrow rounded-full bg-ink px-2 py-0.5 text-lime">Latest</span>}
                              </div>
                              <p className="mt-1 flex items-center gap-1.5 text-sm text-stone"><Icon name="pin" className="size-3.5" />{event.location || 'Location not recorded'}</p>
                            </div>
                            <time className="eyebrow shrink-0 text-mist">{formatDateTime(eventTime(event))}</time>
                          </div>
                          {(event.remarks || event.description) && <p className="mt-3 border-t border-line pt-3 text-sm leading-6 text-graphite">{event.remarks || event.description}</p>}
                        </div>
                      </li>
                    ))}
                  </ol>
                )}
              </Panel>

              {canUpdateTracking && (
                <Panel eyebrow="Field update" title="Record a status" subtitle={`For shipment #${selectedShipment.shipment_id}`} className="2xl:sticky 2xl:top-24 2xl:self-start">
                  {statusOptions.length === 0 ? (
                    <div className="space-y-4">
                      {updateSuccess && <Notice tone="success">{updateSuccess}</Notice>}
                      <Notice tone="info">This shipment is {formatLabel(selectedShipment.shipment_status).toLowerCase()} and closed. Its history is kept, but no further tracking updates can be recorded.</Notice>
                    </div>
                  ) : (
                  <form onSubmit={submitTrackingUpdate} className="space-y-4">
                    {updateError && <Notice tone="error">{updateError}</Notice>}
                    {updateSuccess && <Notice tone="success">{updateSuccess}</Notice>}
                    <label className="block"><span className="field-label">Status</span><select value={statusOptions.includes(status) ? status : statusOptions[0]} onChange={(event) => setStatus(event.target.value)} className="field cursor-pointer">{statusOptions.map((value) => <option key={value} value={value}>{formatLabel(value)}{value === selectedShipment.shipment_status ? ' (checkpoint)' : ''}</option>)}</select></label>
                    <label className="block"><span className="field-label">Location</span><input value={location} onChange={(event) => setLocation(event.target.value)} maxLength={150} placeholder="Current location" className="field" /></label>
                    <label className="block"><span className="field-label">Remarks</span><textarea value={remarks} onChange={(event) => setRemarks(event.target.value)} maxLength={255} rows="3" placeholder="Optional update details" className="field resize-y" /></label>
                    <button type="submit" disabled={updating} className="btn btn-ink w-full py-3!">{updating ? 'Saving update…' : 'Save tracking update'}</button>
                  </form>
                  )}
                </Panel>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function eventTime(event) {
  return event.tracking_timestamp ?? event.tracking_time ?? event.tracking_date ?? event.created_at ?? event.timestamp ?? event.updated_at
}

function ShipmentHero({ shipment }) {
  const status = String(shipment.shipment_status ?? '').toUpperCase()
  const cancelled = status === 'CANCELLED'
  const reached = PROGRESS_STAGES.indexOf(status)
  const progress = reached < 0 ? 0 : (reached / (PROGRESS_STAGES.length - 1)) * 100

  return (
    <section className="on-dark animate-rise relative overflow-hidden rounded-[1.8rem] bg-ink p-6 text-paper sm:p-8">
      <span className="absolute -top-20 -right-20 size-64 rounded-full border-[24px] border-lime/10" aria-hidden="true" />
      <div className="relative flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="eyebrow text-lime">Shipment</p>
          <h2 className="font-display mt-2 text-5xl font-semibold sm:text-6xl">#{shipment.shipment_id}</h2>
          <p className="mt-2 text-paper/60">Order #{shipment.order_id ?? '—'}</p>
        </div>
        <dl className="grid grid-cols-2 gap-x-8 gap-y-4 text-sm sm:grid-cols-3 lg:text-right">
          <div><dt className="eyebrow text-paper/50">Status</dt><dd className="mt-1.5 font-semibold">{formatLabel(shipment.shipment_status, 'Unknown')}</dd></div>
          <div><dt className="eyebrow text-paper/50">Shipped</dt><dd className="mt-1.5 font-semibold">{formatDate(shipment.shipment_date)}</dd></div>
          <div><dt className="eyebrow text-paper/50">{shipment.actual_delivery ? 'Delivered' : 'Estimated'}</dt><dd className="mt-1.5 font-semibold">{formatDate(shipment.actual_delivery ?? shipment.estimated_delivery)}</dd></div>
        </dl>
      </div>

      {cancelled ? (
        <div className="relative mt-8 flex items-center gap-3 rounded-2xl bg-bad/20 px-4 py-3 text-sm font-semibold text-[#ffd2c4]">
          <Icon name="x" className="size-4" /> This shipment was cancelled.
        </div>
      ) : (
        <div className="relative mt-10">
          <div className="absolute top-5 right-5 left-5 h-[3px] rounded-full bg-paper/10" aria-hidden="true">
            <div className="h-full rounded-full bg-lime transition-[width] duration-700" style={{ width: `${progress}%` }} />
          </div>
          <ol className="relative grid grid-cols-5" aria-label="Shipment progress">
            {PROGRESS_STAGES.map((stage, index) => {
              const done = index <= reached
              const current = index === reached
              return (
                <li key={stage} className="flex flex-col items-center text-center" aria-current={current ? 'step' : undefined}>
                  <span className={`grid size-10 place-items-center rounded-full transition-colors ${done ? 'bg-lime text-ink' : 'bg-charcoal text-paper/40 ring-1 ring-paper/15'} ${current ? 'ring-4 ring-lime/30' : ''}`}>
                    <Icon name={STAGE_ICONS[stage]} className="size-4" />
                  </span>
                  <span className={`mt-3 text-[0.7rem] leading-tight font-semibold sm:text-xs ${done ? 'text-paper' : 'text-paper/40'}`}>{formatLabel(stage)}</span>
                </li>
              )
            })}
          </ol>
        </div>
      )}
    </section>
  )
}

export default Tracking
