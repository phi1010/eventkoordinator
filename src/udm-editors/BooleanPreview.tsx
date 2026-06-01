import type { PreviewProps } from './FieldPreview'
import { fieldPreviewRegistry } from './registry-preview'

function BooleanPreview({ value }: PreviewProps) {
  if (value == null) return <span style={{ color: '#9ca3af' }}>—</span>
  return value ? (
    <span style={{ color: '#16a34a', fontWeight: 600, fontSize: '0.9rem' }}>✓ Yes</span>
  ) : (
    <span style={{ color: '#dc2626', fontWeight: 600, fontSize: '0.9rem' }}>✗ No</span>
  )
}

fieldPreviewRegistry.register('boolean', BooleanPreview)
