import type { PreviewProps } from './FieldPreview'
import { fieldPreviewRegistry } from './registry-preview'

function NumberPreview({ fd, value }: PreviewProps) {
  if (value == null) return <span style={{ color: '#9ca3af' }}>—</span>
  const formatted = fd.data_type === 'integer'
    ? (value as number).toLocaleString(undefined, { maximumFractionDigits: 0 })
    : (value as number).toLocaleString(undefined, { maximumFractionDigits: 6 })
  return <span style={{ fontSize: '0.9rem', color: '#374151', fontVariantNumeric: 'tabular-nums' }}>{formatted}</span>
}

fieldPreviewRegistry.register(['integer', 'float'], NumberPreview)
