// Run with: node --test src/lib/status.test.js
import assert from 'node:assert/strict'
import test from 'node:test'
import { DELIVERY_GROUPS, deliveryGroupId, isOpenDelivery, nextShipmentStatuses, summariseDeliveries } from './status.js'

const sample = ['PENDING', 'PENDING', 'OUT_FOR_DELIVERY', 'DELIVERED', 'DELIVERED', 'FAILED', 'CANCELLED'].map((delivery_status, index) => ({ delivery_id: index + 1, delivery_status }))

test('every delivery lands in exactly one group and groups add up to the total', () => {
  const summary = summariseDeliveries(sample)
  assert.equal(Object.values(summary.groups).reduce((a, b) => a + b, 0), summary.total)
  assert.deepEqual(summary.groups, { pending: 2, moving: 1, done: 2, issues: 2 })
  for (const delivery of sample) assert.equal(DELIVERY_GROUPS.filter((group) => group.statuses.includes(delivery.delivery_status)).length, 1)
})

test('dashboard open count agrees with the board: total - delivered - cancelled', () => {
  const summary = summariseDeliveries(sample)
  assert.equal(summary.open, summary.total - summary.delivered - sample.filter((d) => d.delivery_status === 'CANCELLED').length)
  assert.equal(summary.open, summary.groups.pending + summary.groups.moving + sample.filter((d) => d.delivery_status === 'FAILED').length)
  assert.equal(isOpenDelivery({ delivery_status: 'CANCELLED' }), false)
  assert.equal(isOpenDelivery({ delivery_status: 'FAILED' }), true)
})

test('unknown or missing statuses are not silently dropped', () => {
  assert.equal(deliveryGroupId({ delivery_status: 'SOMETHING_NEW' }), 'pending')
  assert.equal(summariseDeliveries([{}]).total, 1)
})

test('tracking options never go backwards and closed shipments offer none', () => {
  assert.deepEqual(nextShipmentStatuses('IN_TRANSIT'), ['IN_TRANSIT', 'OUT_FOR_DELIVERY', 'DELIVERED', 'CANCELLED'])
  assert.deepEqual(nextShipmentStatuses('DELIVERED'), [])
  assert.deepEqual(nextShipmentStatuses('CANCELLED'), [])
})
