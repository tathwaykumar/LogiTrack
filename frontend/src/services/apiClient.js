export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

export async function apiGet(path, accessToken) {
  const response = await fetch(`/api${path}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  })
  const data = await response.json().catch(() => ({}))

  if (!response.ok) throw new ApiError(data.detail || 'Unable to load dashboard data.', response.status)
  return data
}

export async function apiPatch(path, payload, accessToken) {
  const response = await fetch(`/api${path}`, {
    method: 'PATCH',
    headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const data = await response.json().catch(() => ({}))

  if (!response.ok) throw new ApiError(data.detail || 'Unable to update profile.', response.status)
  return data
}

export async function apiPost(path, payload, accessToken) {
  const response = await fetch(`/api${path}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const data = await response.json().catch(() => ({}))

  if (!response.ok) throw new ApiError(data.detail || 'Unable to save tracking update.', response.status)
  return data
}
