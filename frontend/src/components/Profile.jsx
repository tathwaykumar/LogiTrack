import { useCallback, useEffect, useState } from 'react'
import { ApiError, apiGet, apiPatch } from '../services/apiClient.js'

const emptyForm = { username: '', email: '', password: '', current_password: '', name: '', phone: '', address: '' }

function Profile({ session, onAuthExpired, onUsernameUpdated, onPasswordChanged }) {
  const [profile, setProfile] = useState(null)
  const [form, setForm] = useState(emptyForm)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const loadProfile = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await apiGet('/profile', session.accessToken)
      setProfile(data)
      setForm({ username: data.username ?? '', email: data.email ?? '', password: '', current_password: '', name: data.name ?? '', phone: data.phone ?? '', address: data.address ?? '' })
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onAuthExpired()
        return
      }
      setError(err.message || 'Unable to load your profile.')
    } finally {
      setLoading(false)
    }
  }, [session.accessToken, onAuthExpired])

  useEffect(() => { loadProfile() }, [loadProfile])

  function updateField(event) {
    const { name, value } = event.target
    setForm((current) => ({ ...current, [name]: value }))
  }

  async function saveProfile(event) {
    event.preventDefault()
    if (!profile) return
    setSaving(true)
    setError('')
    setSuccess('')
    const payload = {}
    for (const field of ['username', 'email', 'name', 'phone', 'address']) {
      if (form[field] !== (profile[field] ?? '')) payload[field] = form[field]
    }
    if (form.password) {
      payload.password = form.password
      payload.current_password = form.current_password
    }

    if (Object.keys(payload).length === 0) {
      setSuccess('No profile changes to save.')
      setSaving(false)
      return
    }

    try {
      const updated = await apiPatch('/profile', payload, session.accessToken)
      setProfile(updated)
      setForm({ username: updated.username ?? '', email: updated.email ?? '', password: '', current_password: '', name: updated.name ?? '', phone: updated.phone ?? '', address: updated.address ?? '' })
      if (updated.username !== session.user.username) onUsernameUpdated(updated.username)
      if (payload.password) {
        onPasswordChanged()
        return
      }
      setSuccess('Your profile has been updated.')
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onAuthExpired()
        return
      }
      setError(err.message || 'Unable to update your profile.')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div className="mx-auto max-w-3xl space-y-5 animate-pulse"><div className="h-24 rounded-2xl bg-slate-200" /><div className="h-96 rounded-2xl bg-slate-200" /></div>
  if (error && !profile) return <div className="mx-auto max-w-xl rounded-2xl border border-rose-200 bg-white p-7 shadow-sm"><p className="text-lg font-semibold text-slate-950">Profile unavailable</p><p className="mt-2 text-slate-600">{error}</p><button type="button" onClick={loadProfile} className="mt-6 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white hover:bg-slate-800">Try again</button></div>

  const hasPersonalProfile = Boolean(profile?.profile_type)
  const isCustomer = profile?.profile_type === 'CUSTOMER'
  return <div className="mx-auto max-w-3xl space-y-6">
    <div><p className="text-sm font-medium text-cyan-700">Account settings</p><h2 className="mt-1 text-2xl font-bold tracking-tight text-slate-950">My profile</h2><p className="mt-2 text-sm text-slate-500">Update your own account and available contact information.</p></div>
    {error && <div role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">{error}</div>}
    {success && <div role="status" className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-700">{success}</div>}
    <form onSubmit={saveProfile} className="space-y-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
      <section><h3 className="font-semibold text-slate-900">Account details</h3><p className="mt-1 text-sm text-slate-500">Your sign-in identity and contact email.</p><div className="mt-5 grid gap-4 sm:grid-cols-2"><Field label="Username" name="username" value={form.username} onChange={updateField} required /><Field label="Email" name="email" type="email" value={form.email} onChange={updateField} required /></div></section>
      <section className="border-t border-slate-200 pt-6"><h3 className="font-semibold text-slate-900">Password</h3><p className="mt-1 text-sm text-slate-500">Leave blank to keep your current password. A password change requires your current password and signs this browser out.</p><div className="mt-5 grid max-w-xl gap-4 sm:grid-cols-2"><Field label="Current password" name="current_password" type="password" value={form.current_password} onChange={updateField} required={Boolean(form.password)} autoComplete="current-password" /><Field label="New password" name="password" type="password" value={form.password} onChange={updateField} minLength={8} autoComplete="new-password" /></div></section>
      {hasPersonalProfile ? <section className="border-t border-slate-200 pt-6"><h3 className="font-semibold text-slate-900">Personal details</h3><p className="mt-1 text-sm text-slate-500">Contact fields linked to your {isCustomer ? 'customer' : 'employee'} profile.</p><div className="mt-5 grid gap-4 sm:grid-cols-2"><Field label="Name" name="name" value={form.name} onChange={updateField} required /><Field label="Phone" name="phone" type="tel" value={form.phone} onChange={updateField} />{isCustomer && <div className="sm:col-span-2"><Field label="Address" name="address" value={form.address} onChange={updateField} /></div>}</div></section> : <section className="border-t border-slate-200 pt-6"><h3 className="font-semibold text-slate-900">Personal details</h3><p className="mt-1 text-sm text-slate-500">This account is not linked to an employee or customer profile, so only account details can be changed.</p></section>}
      <div className="flex justify-end border-t border-slate-200 pt-5"><button type="submit" disabled={saving} className="rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60">{saving ? 'Saving...' : 'Save changes'}</button></div>
    </form>
  </div>
}

function Field({ label, name, type = 'text', value, onChange, ...props }) {
  return <label className="block text-sm font-medium text-slate-700">{label}<input name={name} type={type} value={value} onChange={onChange} className="mt-2 block w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm text-slate-900 outline-none transition focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100" {...props} /></label>
}

export default Profile
