import { useState } from 'react'
import { Icon, Notice } from './ui.jsx'

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
    {message && <Notice tone="error">{message}</Notice>}
    <Field label="Full name" name="name" value={form.name} onChange={updateField} maxLength={100} disabled={isLoading} autoComplete="name" />
    <div className="grid gap-4 sm:grid-cols-2">
      <Field label="Username" name="username" value={form.username} onChange={updateField} minLength={3} maxLength={50} disabled={isLoading} autoComplete="username" />
      <Field label="Phone number" name="phone" type="tel" value={form.phone} onChange={updateField} minLength={7} maxLength={20} disabled={isLoading} autoComplete="tel" />
    </div>
    <Field label="Email" name="email" type="email" value={form.email} onChange={updateField} maxLength={100} disabled={isLoading} autoComplete="email" />
    <Field label="Address" name="address" value={form.address} onChange={updateField} maxLength={255} disabled={isLoading} autoComplete="street-address" />
    <div className="grid gap-4 sm:grid-cols-2">
      <Field label="Password" name="password" type="password" value={form.password} onChange={updateField} minLength={8} maxLength={128} disabled={isLoading} autoComplete="new-password" />
      <Field label="Confirm password" name="confirmPassword" type="password" value={form.confirmPassword} onChange={updateField} minLength={8} maxLength={128} disabled={isLoading} autoComplete="new-password" />
    </div>
    <button className="btn btn-ink mt-2 w-full justify-between! px-6! py-3.5! text-base!" disabled={isLoading} type="submit"><span className="inline-flex items-center gap-2">{isLoading && <span aria-hidden="true" className="size-4 animate-spin rounded-full border-2 border-paper/40 border-t-paper" />}{isLoading ? 'Creating account…' : 'Create account'}</span><Icon name="arrowRight" className="size-5" /></button>
  </form>
}

function Field({ label, name, type = 'text', value, onChange, ...props }) {
  return <label className="block"><span className="field-label">{label} <span className="text-bad" aria-hidden="true">*</span></span><input className="field py-3!" name={name} onChange={onChange} required type={type} value={value} {...props} /></label>
}

export default SignupForm
