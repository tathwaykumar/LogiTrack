import { useCallback, useEffect, useState } from 'react'
import { ApiError, apiGet, apiPatch } from '../services/apiClient.js'
import { ROLE_NAMES, formatLabel, initials } from '../lib/format.js'
import { ErrorState, Icon, Notice, PageHeader } from './ui.jsx'

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

  if (loading) return <div className="grid gap-6 lg:grid-cols-[22rem_1fr]" aria-busy="true"><div className="h-96 rounded-[1.8rem] bg-ink/90" /><div className="skeleton h-[32rem] rounded-[1.8rem]!" /></div>
  if (error && !profile) return <div className="panel mx-auto max-w-xl"><ErrorState title="Profile unavailable" message={error} onRetry={loadProfile} /></div>

  const hasPersonalProfile = Boolean(profile?.profile_type)
  const isCustomer = profile?.profile_type === 'CUSTOMER'
  const displayName = profile?.name || profile?.username

  return (
    <div className="space-y-8">
      <PageHeader eyebrow="Account settings" title="My" accent="profile." description="Update your own account and available contact information." />

      <div className="grid items-start gap-6 lg:grid-cols-[22rem_minmax(0,1fr)]">
        <aside className="on-dark animate-rise relative overflow-hidden rounded-[1.8rem] bg-ink p-7 text-paper lg:sticky lg:top-24">
          <span className="absolute -top-16 -right-16 size-48 rounded-full border-[22px] border-lime/15" aria-hidden="true" />
          <span className="relative grid size-24 place-items-center rounded-[1.8rem] bg-lime font-display text-4xl font-bold text-ink">{initials(displayName)}</span>
          <h2 className="font-display relative mt-6 text-3xl font-semibold">{displayName}</h2>
          <p className="relative mt-1 text-paper/60">@{profile?.username}</p>
          <dl className="relative mt-8 space-y-4 border-t border-paper/10 pt-6 text-sm">
            <div className="flex items-center justify-between gap-3"><dt className="text-paper/50">Role</dt><dd className="rounded-full bg-lime px-2.5 py-0.5 text-xs font-bold text-ink">{formatLabel(ROLE_NAMES[Number(session.user.roleId)] ?? 'USER')}</dd></div>
            <div className="flex items-center justify-between gap-3"><dt className="text-paper/50">Profile type</dt><dd className="font-semibold">{profile?.profile_type ? formatLabel(profile.profile_type) : 'Account only'}</dd></div>
            <div className="flex items-start justify-between gap-3"><dt className="text-paper/50">Email</dt><dd className="truncate text-right font-semibold">{profile?.email}</dd></div>
            {profile?.phone && <div className="flex items-center justify-between gap-3"><dt className="text-paper/50">Phone</dt><dd className="font-semibold">{profile.phone}</dd></div>}
          </dl>
        </aside>

        <form onSubmit={saveProfile} className="panel animate-rise overflow-hidden" style={{ animationDelay: '80ms' }}>
          {(error || success) && (
            <div className="space-y-3 px-5 pt-5 sm:px-7 sm:pt-6">
              {error && <Notice tone="error">{error}</Notice>}
              {success && <Notice tone="success">{success}</Notice>}
            </div>
          )}
          <FormSection icon="user" first={!(error || success)} title="Account details" text="Your sign-in identity and contact email.">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Username" name="username" value={form.username} onChange={updateField} required autoComplete="username" />
              <Field label="Email" name="email" type="email" value={form.email} onChange={updateField} required autoComplete="email" />
            </div>
          </FormSection>
          <FormSection icon="shield" title="Password" text="Leave blank to keep your current password. A password change requires your current password and signs this browser out.">
            <div className="grid max-w-xl gap-4 sm:grid-cols-2">
              <Field label="Current password" name="current_password" type="password" value={form.current_password} onChange={updateField} required={Boolean(form.password)} autoComplete="current-password" />
              <Field label="New password" name="password" type="password" value={form.password} onChange={updateField} minLength={8} autoComplete="new-password" />
            </div>
          </FormSection>
          {hasPersonalProfile ? (
            <FormSection icon="idcard" title="Personal details" text={`Contact fields linked to your ${isCustomer ? 'customer' : 'employee'} profile.`}>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Name" name="name" value={form.name} onChange={updateField} required autoComplete="name" />
                <Field label="Phone" name="phone" type="tel" value={form.phone} onChange={updateField} autoComplete="tel" />
                {isCustomer && <div className="sm:col-span-2"><Field label="Address" name="address" value={form.address} onChange={updateField} autoComplete="street-address" /></div>}
              </div>
            </FormSection>
          ) : (
            <FormSection icon="idcard" title="Personal details" text="This account is not linked to an employee or customer profile, so only account details can be changed." />
          )}
          <div className="flex justify-end border-t border-line bg-ivory/60 px-5 py-4 sm:px-7">
            <button type="submit" disabled={saving} className="btn btn-ink px-6! py-3!">{saving ? 'Saving…' : 'Save changes'} <Icon name="check" className="size-4" /></button>
          </div>
        </form>
      </div>
    </div>
  )
}

function FormSection({ icon, title, text, children, first = false }) {
  return (
    <section className={`grid gap-5 px-5 py-6 sm:px-7 xl:grid-cols-[15rem_minmax(0,1fr)] ${first ? '' : 'border-t border-line'}`}>
      <div className="flex items-start gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-full bg-cream"><Icon name={icon} className="size-4" /></span>
        <div>
          <h3 className="font-display text-lg font-semibold">{title}</h3>
          <p className="mt-1 text-sm leading-6 text-stone">{text}</p>
        </div>
      </div>
      {children && <div>{children}</div>}
    </section>
  )
}

function Field({ label, name, type = 'text', value, onChange, ...props }) {
  return <label className="block"><span className="field-label">{label}</span><input name={name} type={type} value={value} onChange={onChange} className="field" {...props} /></label>
}

export default Profile
