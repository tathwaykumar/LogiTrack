// Shared display formatters. They only format values returned by the API.

export function formatLabel(value, fallback = '—') {
  if (value === null || value === undefined || value === '') return fallback
  return String(value).replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function toDate(value) {
  if (!value) return null
  const date = new Date(value)
  return Number.isNaN(date.valueOf()) ? null : date
}

export function formatDate(value, fallback = '—') {
  const date = toDate(value)
  return date ? new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }).format(date) : fallback
}

export function formatShortDate(value, fallback = '—') {
  const date = toDate(value)
  return date ? new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short' }).format(date) : fallback
}

export function formatDateTime(value, fallback = 'Time not recorded') {
  const date = toDate(value)
  return date ? new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'short' }).format(date) : fallback
}

export function formatCurrency(value, fallback = '—') {
  if (value === null || value === undefined || value === '') return fallback
  const amount = Number(value)
  return Number.isFinite(amount)
    ? new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: Number.isInteger(amount) ? 0 : 2, maximumFractionDigits: 2 }).format(amount)
    : String(value)
}

export function formatNumber(value, fallback = '—') {
  const number = Number(value)
  return value === null || value === undefined || !Number.isFinite(number) ? fallback : number.toLocaleString('en-IN')
}

export function daysUntil(value) {
  const date = toDate(value)
  if (!date) return null
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return Math.round((date - today) / 86400000)
}

export function initials(value) {
  const parts = String(value ?? '').trim().split(/[\s._-]+/).filter(Boolean)
  return (parts.length > 1 ? parts[0][0] + parts[1][0] : String(value ?? '?').slice(0, 2)).toUpperCase()
}

export const ROLE_NAMES = { 1: 'ADMIN', 2: 'OPERATIONS_MANAGER', 3: 'DRIVER', 4: 'CUSTOMER' }
