import type { PreviewProps } from './FieldPreview'
import { fieldPreviewRegistry } from './registry-preview'

function SelectMultiPreview({ value }: PreviewProps) {
  const items: string[] = Array.isArray(value) ? (value as unknown[]).map(String) : []
  if (items.length === 0) return <span style={{ color: '#9ca3af' }}>—</span>
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
      {items.map(item => (
        <span key={item} style={{ display: 'inline-block', padding: '2px 10px', borderRadius: '999px', fontSize: '0.82rem', fontWeight: 500, background: '#e0e7ff', color: '#3730a3', border: '1px solid #c7d2fe' }}>
          {item}
        </span>
      ))}
    </div>
  )
}

fieldPreviewRegistry.register('select_multi', SelectMultiPreview)
