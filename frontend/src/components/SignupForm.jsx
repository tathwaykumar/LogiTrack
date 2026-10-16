import { useState } from 'react'

const initialForm = { name: '', username: '', email: '', phone: '', address: '', password: '', confirmPassword: '' }

function SignupForm({ onSubmit, isLoading, error }) {
  const [form, setForm] = useState(initialForm)
  const [validationError, setValidationError] = useState('')

  function updateField(event) {
    const { name, value } = event.target
    setForm((current) => ({ ...current, [name]: value }))
  }

  function submit(event) {
    event.preventDefault()
    const values = Object.fromEntries(Object.entries(form).map(([key, value]) => [key, value.trim()]))
    if (Object.values(values).some((value) => !value)) return setValidationError('All fields are required.')
    if (!/^\S+@\S+\.\S+$/.test(values.email)) return setValidationError('Enter a valid email address.')
    if (values.username.length < 3 || values.username.length > 50) return setValidationError('Username must be 3 to 50 characters.')
    if (values.phone.length < 7 || values.phone.length > 20) return setValidationError('Phone number must be 7 to 20 characters.')
    if (form.password.length < 8) return setValidationError('Password must be at least 8 characters.')
    if (form.password !== form.confirmPassword) return setValidationError('Passwords do not match.')
    setValidationError('')
    onSubmit({ ...values, password: form.password })
  }

  const message = validationError || error
  return <form className="mt-8 space-y-4" onSubmit={submit}>
    {message && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm leading-6 text-red-700">{message}</div>}
    <Field label="Full name" name="name" value={form.name} onChange={updateField} maxLength={100} disabled={isLoading} autoComplete="name" />
    <Field label="Username" name="username" value={form.username} onChange={updateField} minLength={3} maxLength={50} disabled={isLoading} autoComplete="username" />
    <Field label="Email" name="email" type="email" value={form.email} onChange={updateField} maxLength={100} disabled={isLoading} autoComplete="email" />
    <Field label="Phone number" name="phone" type="tel" value={form.phone} onChange={updateField} minLength={7} maxLength={20} disabled={isLoading} autoComplete="tel" />
    <Field label="Address" name="address" value={form.address} onChange={updateField} maxLength={255} disabled={isLoading} autoComplete="street-address" />
    <Field label="Password" name="password" type="password" value={form.password} onChange={updateField} minLength={8} maxLength={128} disabled={isLoading} autoComplete="new-password" />
    <Field label="Confirm password" name="confirmPassword" type="password" value={form.confirmPassword} onChange={updateField} minLength={8} maxLength={128} disabled={isLoading} autoComplete="new-password" />
    <button className="flex w-full items-center justify-center gap-2 rounded-xl bg-slate-900 px-4 py-3 font-semibold text-white shadow-sm transition hover:bg-slate-800 focus:outline-none focus:ring-4 focus:ring-slate-300 disabled:cursor-wait disabled:opacity-70" disabled={isLoading} type="submit">{isLoading && <span aria-hidden="true" className="size-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />}{isLoading ? 'Creating account...' : 'Create account'}</button>
  </form>
}

function Field({ label, name, type = 'text', value, onChange, ...props }) {
  return <label className="block"><span className="mb-2 block text-sm font-medium text-slate-800">{label} <span className="text-rose-600">*</span></span><input className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-slate-950 outline-none transition placeholder:text-slate-400 focus:border-cyan-600 focus:ring-4 focus:ring-cyan-100" name={name} onChange={onChange} required type={type} value={value} {...props} /></label>
}

export default SignupForm
