import type { PreviewProps } from './FieldPreview'
import { fieldPreviewRegistry } from './registry-preview'

function DateTimePreview({ fd, value }: PreviewProps) {
  if (value == null) return <span style={{ color: '#9ca3af' }}>—</span>
  const raw = value as string
  let display = raw
  try {
    if (fd.data_type === 'date') {
      display = new Date(raw).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
    } else if (fd.data_type === 'time') {
      const [h, m] = raw.split(':')
      display = `${h}:${m}`
    } else {
      display = new Date(raw).toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
    }
  } catch {
    display = raw
  }
  return <span style={{ fontSize: '0.9rem', color: '#374151', fontVariantNumeric: 'tabular-nums' }}>{display}</span>
}

fieldPreviewRegistry.register(['date', 'time', 'datetime'], DateTimePreview)
