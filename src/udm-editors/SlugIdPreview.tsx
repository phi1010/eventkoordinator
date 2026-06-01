import type { PreviewProps } from './FieldPreview'
import { fieldPreviewRegistry } from './registry-preview'

function SlugIdPreview({ fd, value }: PreviewProps) {
  if (value == null) return <span style={{ color: '#9ca3af' }}>—</span>
  const prefix = ((fd.type_config as Record<string, unknown>)?.['prefix'] as string) ?? ''
  const display = prefix ? `${prefix}-${value}` : String(value)
  return (
    <span style={{ fontFamily: 'monospace', fontSize: '0.88rem', color: '#374151', background: '#f3f4f6', padding: '1px 5px', borderRadius: 3 }}>
      {display}
    </span>
  )
}

fieldPreviewRegistry.register('slug_id', SlugIdPreview)
