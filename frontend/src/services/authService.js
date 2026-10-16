const AUTH_STORAGE_KEY = 'logitrack.auth'

export async function login({ username, password }) {
  const response = await fetch('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })

  const data = await response.json().catch(() => ({}))

  if (!response.ok) {
    throw new Error(data.detail || 'Unable to sign in. Please try again.')
  }

  const session = {
    accessToken: data.access_token,
    tokenType: data.token_type,
    user: { id: data.user_id, username: data.username, roleId: data.role_id },
  }

  localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(session))
  return session
}

export async function registerAccount({ name, username, email, phone, address, password }) {
  const response = await fetch('/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, username, email, phone, address, password }),
  })

  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data.detail || 'Unable to create your account. Please try again.')
  return data
}

export { AUTH_STORAGE_KEY }
