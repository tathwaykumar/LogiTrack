import { useState } from 'react'
import AppShell from './components/AppShell.jsx'
import LoginPage from './components/LoginPage.jsx'
import { AUTH_STORAGE_KEY } from './services/authService.js'

const ROLE_NAMES = { 1: 'ADMIN', 2: 'OPERATIONS_MANAGER', 3: 'DRIVER', 4: 'CUSTOMER' }

function App() {
  const [session, setSession] = useState(readSession)

  function handleLogout() {
    localStorage.removeItem(AUTH_STORAGE_KEY)
    setSession(null)
  }

  return session ? <AppShell session={session} onLogout={handleLogout} /> : <LoginPage onAuthenticated={setSession} />
}

function readSession() {
  try {
    const session = JSON.parse(localStorage.getItem(AUTH_STORAGE_KEY))
    if (session?.accessToken && session?.user?.username && Number(session.user.roleId) in ROLE_NAMES) return session
  } catch {
    // An invalid stored value is treated as an unauthenticated session.
  }
  return null
}

export default App
