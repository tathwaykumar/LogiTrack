
import { useCallback, useEffect, useState } from 'react'
import { ApiError, apiGet, apiPost } from '../services/apiClient.js'

const TRACKING_STATUSES = ['CREATED', 'PICKED_UP', 'IN_TRANSIT', 'OUT_FOR_DELIVERY', 'DELIVERED', 'CANCELLED']

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
        const data = await apiGet(
          `/shipments/${selectedId}/timeline`,
          session.accessToken
        )

        if (active) {
          const timeline = Array.isArray(data)
            ? data
            : data.timeline ?? data.tracking ?? data.events ?? []

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

        setTimelineError(
          err.message || 'Unable to load this shipment timeline.'
        )
      } finally {
        if (active) setLoadingTimeline(false)
      }
    }

    loadTimeline()

    return () => {
      active = false
    }
  }, [selectedId, session.accessToken, onAuthExpired])

  const selectedShipment = shipments.find(
    (item) => String(item.shipment_id) === selectedId
  )

  async function submitTrackingUpdate(event) {
    event.preventDefault()
    if (!selectedId) return
    setUpdating(true)
    setUpdateError('')
    setUpdateSuccess('')

    try {
      const data = await apiPost('/tracking', {
        shipment_id: Number(selectedId),
        status,
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
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.16em] text-cyan-700">
            Shipment visibility
          </p>
          <h2 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">
            Tracking
          </h2>
          <p className="mt-2 text-slate-600">
            Follow shipment status, locations and tracking history.
          </p>
        </div>

        <button
          onClick={() => setRefreshKey((key) => key + 1)}
          disabled={loadingShipments}
          className="rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:opacity-50"
        >
          {loadingShipments ? 'Refreshing...' : 'Refresh tracking'}
        </button>
      </div>

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
        <label
          htmlFor="tracking-shipment"
          className="block text-sm font-semibold text-slate-800"
        >
          Select shipment
        </label>

        {loadingShipments ? (
          <div className="mt-3 h-11 animate-pulse rounded-lg bg-slate-100" />
        ) : error ? (
          <div className="mt-4 rounded-xl bg-red-50 p-4">
            <p className="text-sm text-red-700">{error}</p>
            <button
              onClick={() => setRefreshKey((key) => key + 1)}
              className="mt-3 text-sm font-semibold text-red-800 underline"
            >
              Try again
            </button>
          </div>
        ) : shipments.length === 0 ? (
          <div className="mt-4 rounded-xl bg-slate-50 px-4 py-8 text-center">
            <p className="font-semibold text-slate-900">
              No shipments available
            </p>
            <p className="mt-2 text-sm text-slate-500">
              Tracking history will appear here when you have a shipment.
            </p>
          </div>
        ) : (
          <select
            id="tracking-shipment"
            value={selectedId}
            onChange={(event) => setSelectedId(event.target.value)}
            className="mt-3 w-full rounded-lg border border-slate-300 bg-white px-3 py-3 text-sm outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100 sm:max-w-md"
          >
            {shipments.map((shipment) => (
              <option
                key={shipment.shipment_id}
                value={String(shipment.shipment_id)}
              >
                Shipment #{shipment.shipment_id} — {shipment.shipment_status ?? 'Unknown status'}
              </option>
            ))}
          </select>
        )}
      </section>

      {selectedShipment && (
        <div className="grid gap-4 sm:grid-cols-3">
          <SummaryCard
            label="Shipment ID"
            value={`#${selectedShipment.shipment_id}`}
          />
          <SummaryCard
            label="Order ID"
            value={selectedShipment.order_id ?? '—'}
          />
          <SummaryCard
            label="Current status"
            value={formatLabel(selectedShipment.shipment_status)}
          />
        </div>
      )}

      {selectedShipment && canUpdateTracking && (
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
          <div>
            <h3 className="font-semibold text-slate-950">Update tracking status</h3>
            <p className="mt-1 text-sm text-slate-500">Record the latest status for shipment #{selectedShipment.shipment_id}.</p>
          </div>
          {updateError && <div role="alert" className="mt-4 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">{updateError}</div>}
          {updateSuccess && <div role="status" className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-700">{updateSuccess}</div>}
          <form onSubmit={submitTrackingUpdate} className="mt-5 grid gap-4 sm:grid-cols-2">
            <label className="block text-sm font-medium text-slate-700">Status<select value={status} onChange={(event) => setStatus(event.target.value)} className="mt-2 block w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100">{TRACKING_STATUSES.map((value) => <option key={value} value={value}>{formatLabel(value)}</option>)}</select></label>
            <label className="block text-sm font-medium text-slate-700">Location<input value={location} onChange={(event) => setLocation(event.target.value)} maxLength={150} placeholder="Current location" className="mt-2 block w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm text-slate-900 outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100" /></label>
            <label className="block text-sm font-medium text-slate-700 sm:col-span-2">Remarks<textarea value={remarks} onChange={(event) => setRemarks(event.target.value)} maxLength={255} rows="3" placeholder="Optional update details" className="mt-2 block w-full resize-y rounded-xl border border-slate-300 px-3 py-2.5 text-sm text-slate-900 outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100" /></label>
            <div className="sm:col-span-2"><button type="submit" disabled={updating} className="rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60">{updating ? 'Saving update...' : 'Save tracking update'}</button></div>
          </form>
        </section>
      )}

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
        <div>
          <h3 className="font-semibold text-slate-950">Tracking timeline</h3>
          <p className="mt-1 text-sm text-slate-500">
            Recorded events for the selected shipment.
          </p>
        </div>

        {loadingTimeline ? (
          <div className="mt-6 space-y-4">
            {[1, 2, 3].map((item) => (
              <div
                key={item}
                className="h-16 animate-pulse rounded-lg bg-slate-100"
              />
            ))}
          </div>
        ) : timelineError ? (
          <div className="mt-5 rounded-xl border border-red-200 bg-red-50 p-4">
            <p className="font-semibold text-red-800">
              Unable to load tracking history
            </p>
            <p className="mt-1 text-sm text-red-700">{timelineError}</p>
            <button
              onClick={() => setRefreshKey((key) => key + 1)}
              className="mt-3 text-sm font-semibold text-red-800 underline"
            >
              Reload shipments
            </button>
          </div>
        ) : !selectedId ? (
          <EmptyState text="Select a shipment to view its tracking history." />
        ) : events.length === 0 ? (
          <EmptyState text="No tracking events have been recorded for this shipment yet." />
        ) : (
          <div className="mt-6 space-y-0">
            {events.map((event, index) => (
              <div
                key={event.tracking_id ?? event.id ?? index}
                className="relative flex gap-4 pb-7 last:pb-0"
              >
                <div className="flex flex-col items-center">
                  <span className="relative z-10 mt-1 size-3 shrink-0 rounded-full border-2 border-cyan-600 bg-white" />
                  {index !== events.length - 1 && (
                    <span className="absolute bottom-0 top-4 w-px bg-slate-200" />
                  )}
                </div>

                <div className="min-w-0 flex-1 rounded-xl border border-slate-200 p-4">
                  <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-start">
                    <div>
                      <p className="font-semibold text-slate-900">
                        {formatLabel(event.status ?? event.tracking_status)}
                      </p>
                      <p className="mt-1 text-sm text-slate-600">
                        {event.location || 'Location not recorded'}
                      </p>
                    </div>
                    <time className="shrink-0 text-xs text-slate-500">
                      {formatDateTime(
                        event.tracking_time ??
                        event.tracking_date ??
                        event.created_at ??
                        event.timestamp ??
                        event.updated_at
                      )}
                    </time>
                  </div>

                  {(event.remarks || event.description) && (
                    <p className="mt-3 text-sm leading-6 text-slate-600">
                      {event.remarks || event.description}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

function SummaryCard({ label, value }) {
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <p className="text-sm font-medium text-slate-500">{label}</p>
      <p className="mt-2 truncate text-xl font-semibold text-slate-950">
        {value}
      </p>
    </article>
  )
}

function EmptyState({ text }) {
  return (
    <p className="mt-6 rounded-xl bg-slate-50 px-4 py-10 text-center text-sm text-slate-500">
      {text}
    </p>
  )
}

function formatLabel(value) {
  return String(value || 'Unknown')
    .replaceAll('_', ' ')
    .toLowerCase()
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function formatDateTime(value) {
  if (!value) return 'Time not recorded'

  const date = new Date(value)

  return Number.isNaN(date.valueOf())
    ? 'Time not recorded'
    : new Intl.DateTimeFormat('en-IN', {
        dateStyle: 'medium',
        timeStyle: 'short',
      }).format(date)
}

export default Tracking
