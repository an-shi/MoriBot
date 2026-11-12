export function formatUptime(
  seconds: number | null | undefined,
  locale: string,
  justStartedLabel: string,
): string {
  if (!seconds || seconds < 1) {
    return justStartedLabel
  }

  const formatter = (unit: 'day' | 'hour' | 'minute' | 'second') =>
    new Intl.NumberFormat(locale, {
      style: 'unit',
      unit,
      unitDisplay: 'long',
      maximumFractionDigits: 0,
    })

  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)

  if (days > 0) {
    const parts = [formatter('day').format(days)]
    if (hours > 0) {
      parts.push(formatter('hour').format(hours))
    }
    return parts.join(' ')
  }
  if (hours > 0) {
    const parts = [formatter('hour').format(hours)]
    if (minutes > 0) {
      parts.push(formatter('minute').format(minutes))
    }
    return parts.join(' ')
  }
  if (minutes > 0) {
    return formatter('minute').format(minutes)
  }
  return formatter('second').format(Math.max(1, Math.floor(seconds)))
}

export function formatDateTime(
  value: string | null | undefined,
  locale: string,
  emptyLabel: string,
): string {
  if (!value) {
    return emptyLabel
  }
  // The API stores naive UTC timestamps; treat them as UTC before formatting
  // into the viewer's local timezone.
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`
  const date = new Date(normalized)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return new Intl.DateTimeFormat(locale, {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}
