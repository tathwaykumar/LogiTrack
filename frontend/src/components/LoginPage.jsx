import { useState } from 'react'
import { login, registerAccount } from '../services/authService.js'
import LoginForm from './LoginForm.jsx'
import SignupForm from './SignupForm.jsx'

function LoginPage({ onAuthenticated }) {
  const [mode, setMode] = useState('login')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [registrationSuccess, setRegistrationSuccess] = useState('')

  async function handleLogin(credentials) {
    setError('')
    setIsLoading(true)
    try {
      onAuthenticated(await login(credentials))
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setIsLoading(false)
    }
  }

  async function handleRegistration(details) {
    setError('')
    setIsLoading(true)
    try {
      const result = await registerAccount(details)
      setRegistrationSuccess(`Account created for ${result.username}. You can now sign in.`)
      setMode('login')
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setIsLoading(false)
    }
  }

  function showSignup() { setError(''); setRegistrationSuccess(''); setMode('signup') }
  function showLogin() { setError(''); setMode('login') }

  return <main className="min-h-screen bg-slate-950 text-slate-900"><div className="grid min-h-screen lg:grid-cols-[1.1fr_0.9fr]"><section className="relative hidden overflow-hidden bg-slate-900 px-12 py-14 text-white lg:flex lg:flex-col lg:justify-between"><div className="absolute inset-0 opacity-40 [background-image:linear-gradient(rgba(148,163,184,.13)_1px,transparent_1px),linear-gradient(90deg,rgba(148,163,184,.13)_1px,transparent_1px)] [background-size:42px_42px]" /><div className="relative flex items-center gap-3 text-lg font-semibold tracking-tight"><BrandMark />LogiTrack</div><div className="relative max-w-xl"><p className="mb-4 text-sm font-semibold uppercase tracking-[0.2em] text-cyan-300">Operations control center</p><h1 className="text-5xl font-semibold leading-tight tracking-tight">Every shipment, clearly in view.</h1><p className="mt-6 max-w-lg text-lg leading-8 text-slate-300">Coordinate routes, deliveries, and inventory from one secure logistics workspace.</p></div><p className="relative text-sm text-slate-400">&copy; {new Date().getFullYear()} LogiTrack. Built for reliable operations.</p></section><section className="flex min-h-screen items-center justify-center bg-slate-50 px-5 py-10 sm:px-8"><div className="w-full max-w-md"><div className="mb-10 flex items-center gap-3 lg:hidden"><BrandMark /><span className="text-lg font-semibold tracking-tight text-slate-900">LogiTrack</span></div>{mode === 'signup' ? <><p className="text-sm font-semibold uppercase tracking-[0.18em] text-cyan-700">Create your customer account</p><h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">Sign up for LogiTrack</h2><p className="mt-3 text-slate-600">Create an account to place orders and follow your shipments.</p><SignupForm error={error} isLoading={isLoading} onSubmit={handleRegistration} /><p className="mt-6 text-center text-sm text-slate-600">Already have an account? <button type="button" onClick={showLogin} className="font-semibold text-cyan-700 hover:text-cyan-800">Back to Login</button></p></> : <><p className="text-sm font-semibold uppercase tracking-[0.18em] text-cyan-700">Welcome back</p><h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">Sign in to LogiTrack</h2><p className="mt-3 text-slate-600">Enter your account details to access your operations workspace.</p>{registrationSuccess && <div role="status" className="mt-5 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm leading-6 text-emerald-700">{registrationSuccess}</div>}<LoginForm error={error} isLoading={isLoading} onSubmit={handleLogin} /><p className="mt-6 text-center text-sm text-slate-600">Don't have an account? <button type="button" onClick={showSignup} className="font-semibold text-cyan-700 hover:text-cyan-800">Sign Up</button></p></>}</div></section></div></main>
}

function BrandMark() { return <span className="grid size-10 place-items-center rounded-xl bg-cyan-400 text-slate-950"><svg aria-hidden="true" className="size-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M3 6h11v11H3zM14 9h3l4 4v4h-7zM7 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM18 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z" /></svg></span> }

export default LoginPage
