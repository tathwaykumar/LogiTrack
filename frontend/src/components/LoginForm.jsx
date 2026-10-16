import { useState } from 'react'

function LoginForm({ error, isLoading, onSubmit }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  function handleSubmit(event) { event.preventDefault(); onSubmit({ username: username.trim(), password }) }
  return <form className="mt-8 space-y-5" onSubmit={handleSubmit}>
    {error && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm leading-6 text-red-700">{error}</div>}
    <label className="block"><span className="mb-2 block text-sm font-medium text-slate-800">Username</span><input autoComplete="username" className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-slate-950 outline-none transition placeholder:text-slate-400 focus:border-cyan-600 focus:ring-4 focus:ring-cyan-100" disabled={isLoading} onChange={(event) => setUsername(event.target.value)} placeholder="Enter your username" required value={username} /></label>
    <label className="block"><span className="mb-2 block text-sm font-medium text-slate-800">Password</span><span className="relative block"><input autoComplete="current-password" className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 pr-20 text-slate-950 outline-none transition placeholder:text-slate-400 focus:border-cyan-600 focus:ring-4 focus:ring-cyan-100" disabled={isLoading} onChange={(event) => setPassword(event.target.value)} placeholder="Enter your password" required type={showPassword ? 'text' : 'password'} value={password} /><button aria-label={showPassword ? 'Hide password' : 'Show password'} className="absolute inset-y-0 right-0 px-4 text-sm font-semibold text-cyan-700 hover:text-cyan-800 disabled:cursor-not-allowed" disabled={isLoading} onClick={() => setShowPassword((visible) => !visible)} type="button">{showPassword ? 'Hide' : 'Show'}</button></span></label>
    <button className="flex w-full items-center justify-center gap-2 rounded-xl bg-slate-900 px-4 py-3 font-semibold text-white shadow-sm transition hover:bg-slate-800 focus:outline-none focus:ring-4 focus:ring-slate-300 disabled:cursor-wait disabled:opacity-70" disabled={isLoading} type="submit">{isLoading && <span aria-hidden="true" className="size-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />}{isLoading ? 'Signing in…' : 'Sign in'}</button>
  </form>
}

export default LoginForm
