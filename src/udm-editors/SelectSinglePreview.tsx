import type { PreviewProps } from './FieldPreview'
import { fieldPreviewRegistry } from './registry-preview'

function SelectSinglePreview({ value }: PreviewProps) {
  if (value == null || value === '') return <span style={{ color: '#9ca3af' }}>—</span>
  return (
    <span style={{ display: 'inline-block', padding: '2px 10px', borderRadius: '999px', fontSize: '0.82rem', fontWeight: 500, background: '#e0e7ff', color: '#3730a3', border: '1px solid #c7d2fe' }}>
      {String(value)}
    </span>
  )
}

fieldPreviewRegistry.register('select_single', SelectSinglePreview)
