import { Chip } from 'primereact/chip'
import type { PreviewProps } from './FieldPreview'
import { fieldPreviewRegistry } from './registry-preview'

function SelectMultiPreview({ value }: PreviewProps) {
  const items: string[] = Array.isArray(value) ? (value as unknown[]).map(String) : []
  if (items.length === 0) return <span style={{ color: '#9ca3af' }}>—</span>
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
      {items.map(item => <Chip key={item} label={item} style={{ fontSize: '0.82rem' }} />)}
    </div>
  )
}

fieldPreviewRegistry.register('select_multi', SelectMultiPreview)
