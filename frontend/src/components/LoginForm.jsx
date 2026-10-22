import { useState } from 'react'
import { Icon, Notice } from './ui.jsx'

function LoginForm({ error, isLoading, onSubmit }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  function handleSubmit(event) { event.preventDefault(); onSubmit({ username: username.trim(), password }) }
  return <form className="mt-8 space-y-5" onSubmit={handleSubmit}>
    {error && <Notice tone="error">{error}</Notice>}
    <label className="block"><span className="field-label">Username</span><input autoComplete="username" className="field py-3!" disabled={isLoading} onChange={(event) => setUsername(event.target.value)} placeholder="Enter your username" required value={username} /></label>
    <label className="block"><span className="field-label">Password</span><span className="relative block"><input autoComplete="current-password" className="field py-3! pr-20" disabled={isLoading} onChange={(event) => setPassword(event.target.value)} placeholder="Enter your password" required type={showPassword ? 'text' : 'password'} value={password} /><button aria-label={showPassword ? 'Hide password' : 'Show password'} className="absolute inset-y-1 right-1 rounded-xl px-3 text-sm font-semibold text-stone hover:bg-cream hover:text-ink disabled:cursor-not-allowed" disabled={isLoading} onClick={() => setShowPassword((visible) => !visible)} type="button">{showPassword ? 'Hide' : 'Show'}</button></span></label>
    <button className="btn btn-ink w-full justify-between! px-6! py-3.5! text-base!" disabled={isLoading} type="submit"><span className="inline-flex items-center gap-2">{isLoading && <span aria-hidden="true" className="size-4 animate-spin rounded-full border-2 border-paper/40 border-t-paper" />}{isLoading ? 'Signing in…' : 'Sign in'}</span><Icon name="arrowRight" className="size-5" /></button>
  </form>
}

export default LoginForm
