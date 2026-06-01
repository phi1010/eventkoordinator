import type { PreviewProps } from './FieldPreview'
import { fieldPreviewRegistry } from './registry-preview'

function SelectSinglePreview({ value }: PreviewProps) {
  if (value == null || value === '') return <span style={{ color: '#9ca3af' }}>—</span>
  return <span style={{ fontSize: '0.9rem', color: '#374151' }}>{String(value)}</span>
}

fieldPreviewRegistry.register('select_single', SelectSinglePreview)
