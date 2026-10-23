export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

const TECHNICAL = /psycopg|sqlalchemy|sqlstate|integrityerror|traceback|internal server error|\bLT\d{3}\b/i

/**
 * Turn whatever the server sent into a sentence a person can act on.
 * The API's own messages are already plain language; validation arrays, database or server text and
 * bare status codes are not, so those are replaced rather than shown.
 */
export function friendlyError(detail, status, fallback = 'Something went wrong. Please try again.') {
  if (typeof detail === 'string' && detail.trim() && !TECHNICAL.test(detail)) return detail
  if (Array.isArray(detail) || (detail && typeof detail === 'object')) return 'Some of the details are missing or not valid. Please check them and try again.'
  if (status === 401) return 'Your session has expired. Please sign in again.'
  if (status === 403) return 'You do not have permission to do that.'
  if (status === 404) return 'We could not find what you asked for.'
  if (status === 409) return 'This was just changed elsewhere. Refresh and try again.'
  if (status === 422) return 'Some of the details are missing or not valid. Please check them and try again.'
  if (status >= 500) return 'Something went wrong on our side. Please try again in a moment.'
  return fallback
}

async function request(path, accessToken, { method = 'GET', payload, fallback }) {
  let response
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${accessToken}`,
        ...(payload === undefined ? {} : { 'Content-Type': 'application/json' }),
      },
      ...(payload === undefined ? {} : { body: JSON.stringify(payload) }),
    })
  } catch {
    throw new ApiError('We could not reach the server. Check your connection and try again.', 0)
  }
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new ApiError(friendlyError(data.detail, response.status, fallback), response.status)
  return data
}

export const apiGet = (path, accessToken) => request(path, accessToken, { fallback: 'Unable to load this information.' })
export const apiPatch = (path, payload, accessToken) => request(path, accessToken, { method: 'PATCH', payload, fallback: 'Unable to update.' })
export const apiPost = (path, payload, accessToken) => request(path, accessToken, { method: 'POST', payload, fallback: 'Unable to save the update.' })
export const apiPut = (path, payload, accessToken) => request(path, accessToken, { method: 'PUT', payload, fallback: 'Unable to save the change.' })

/** Build a query string from an object, skipping empty values. */
export function queryString(params) {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}
