import assert from 'node:assert/strict'
import { test } from 'node:test'
import { friendlyError } from './apiClient.js'

test('plain-language API messages pass through unchanged', () => {
  assert.equal(friendlyError('This order is cancelled.', 409), 'This order is cancelled.')
})

test('validation arrays, database text and bare status codes never reach the screen', () => {
  const generic = 'Some of the details are missing or not valid. Please check them and try again.'
  assert.equal(friendlyError([{ loc: ['body', 'quantity'], msg: 'field required' }], 422), generic)
  assert.equal(friendlyError(undefined, 422), generic)
  assert.match(friendlyError('(psycopg2.errors.UniqueViolation) duplicate key', 500), /Something went wrong on our side/)
  assert.match(friendlyError('LT409: status cannot go backwards', 409), /changed elsewhere/)
  assert.match(friendlyError('', 403), /permission/)
  assert.match(friendlyError(undefined, 503), /Something went wrong on our side/)
  assert.equal(friendlyError(undefined, 400, 'Unable to save.'), 'Unable to save.')
})
