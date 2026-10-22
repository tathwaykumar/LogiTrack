import { useState } from 'react'
import { login, registerAccount } from '../services/authService.js'
import LoginForm from './LoginForm.jsx'
import SignupForm from './SignupForm.jsx'
import { BrandMark, Icon, Notice, Wordmark } from './ui.jsx'

const FEATURES = [
  ['route', 'Live shipment tracking', 'Every milestone from warehouse to doorstep.'],
  ['shop', 'Built-in storefront', 'Stock is reserved the moment an order is placed.'],
  ['truck', 'Fleet & driver control', 'Assign drivers and vehicles with confidence.'],
]

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

  return (
    <main className="min-h-screen p-3 sm:p-4">
      <div className="grid min-h-[calc(100vh-1.5rem)] gap-3 sm:min-h-[calc(100vh-2rem)] sm:gap-4 lg:grid-cols-[1.15fr_0.85fr]">
        <section className="on-dark relative hidden overflow-hidden rounded-[2rem] bg-ink p-10 text-paper lg:flex lg:flex-col lg:justify-between xl:p-14">
          <svg className="absolute inset-0 size-full text-paper/[0.06]" aria-hidden="true">
            <defs><pattern id="login-grid" width="56" height="56" patternUnits="userSpaceOnUse"><path d="M56 0H0v56" fill="none" stroke="currentColor" /></pattern></defs>
            <rect width="100%" height="100%" fill="url(#login-grid)" />
          </svg>
          <svg className="absolute inset-0 size-full" viewBox="0 0 600 700" preserveAspectRatio="none" aria-hidden="true">
            <path d="M-20 530 C 150 470, 200 500, 320 480 S 500 420, 640 370" fill="none" stroke="#d4f53c" strokeWidth="2.5" strokeDasharray="8 14" style={{ animation: 'dash 2.6s linear infinite' }} />
            <circle cx="320" cy="480" r="7" fill="#d4f53c" />
            <circle cx="320" cy="480" r="18" fill="none" stroke="#d4f53c" strokeOpacity="0.35" strokeWidth="2" />
          </svg>

          <div className="relative flex items-center gap-3">
            <BrandMark className="size-11" />
            <Wordmark className="text-2xl" />
          </div>

          <div className="relative max-w-2xl">
            <p className="eyebrow text-lime">Logistics operating system</p>
            <h1 className="font-display mt-5 text-6xl leading-[0.9] font-semibold xl:text-[5.5rem]">
              Every parcel, <span className="font-serif-accent font-normal text-lime">accounted</span> for.
            </h1>
            <p className="mt-6 max-w-lg text-lg leading-8 text-paper/65">Orders, inventory, routes, drivers and deliveries — coordinated from one calm, precise workspace.</p>
          </div>

          <ul className="relative grid gap-3 xl:grid-cols-3">
            {FEATURES.map(([icon, title, text]) => (
              <li key={title} className="rounded-2xl border border-paper/10 bg-paper/[0.04] p-4">
                <span className="grid size-9 place-items-center rounded-full bg-lime text-ink"><Icon name={icon} className="size-4" /></span>
                <p className="mt-3 text-sm font-semibold text-paper">{title}</p>
                <p className="mt-1 text-xs leading-5 text-paper/55">{text}</p>
              </li>
            ))}
          </ul>
        </section>

        <section className="flex items-center justify-center rounded-[2rem] border border-line bg-paper px-5 py-10 shadow-[var(--shadow-card)] sm:px-10">
          <div className="animate-rise w-full max-w-md" key={mode}>
            <div className="mb-10 flex items-center gap-3 lg:hidden">
              <BrandMark />
              <Wordmark tone="dark" className="text-2xl" />
            </div>
            {mode === 'signup' ? (
              <>
                <p className="eyebrow text-stone">Create your customer account</p>
                <h2 className="font-display mt-3 text-4xl leading-none font-semibold sm:text-5xl">Join <span className="font-serif-accent font-normal">LogiTrack.</span></h2>
                <p className="mt-4 text-stone">Create an account to place orders and follow your shipments.</p>
                <SignupForm error={error} isLoading={isLoading} onSubmit={handleRegistration} />
                <p className="mt-6 text-center text-sm text-stone">Already have an account? <button type="button" onClick={showLogin} className="font-semibold text-ink underline decoration-lime decoration-2 underline-offset-4 hover:decoration-ink">Back to login</button></p>
              </>
            ) : (
              <>
                <p className="eyebrow text-stone">Welcome back</p>
                <h2 className="font-display mt-3 text-4xl leading-none font-semibold sm:text-5xl">Sign in to <span className="font-serif-accent font-normal">your workspace.</span></h2>
                <p className="mt-4 text-stone">Enter your account details to access your operations workspace.</p>
                {registrationSuccess && <div className="mt-6"><Notice tone="success">{registrationSuccess}</Notice></div>}
                <LoginForm error={error} isLoading={isLoading} onSubmit={handleLogin} />
                <p className="mt-6 text-center text-sm text-stone">Don&apos;t have an account? <button type="button" onClick={showSignup} className="font-semibold text-ink underline decoration-lime decoration-2 underline-offset-4 hover:decoration-ink">Sign up</button></p>
              </>
            )}
          </div>
        </section>
      </div>
    </main>
  )
}

export default LoginPage
