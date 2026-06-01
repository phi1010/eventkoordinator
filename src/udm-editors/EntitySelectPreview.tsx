import type { PreviewProps } from './FieldPreview'
import { fieldPreviewRegistry } from './registry-preview'

function EntityChip({ id }: { id: string }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 8px', borderRadius: '999px', fontSize: '0.82rem', background: '#f0f9ff', color: '#0c4a6e', border: '1px solid #bae6fd', fontFamily: 'monospace' }}>
      ⬡ {id.slice(0, 8)}…
    </span>
  )
}

function EntitySelectPreview({ fd, value }: PreviewProps) {
  const multi = fd.data_type === 'entity_select_multi'
  const ids: string[] = multi
    ? (Array.isArray(value) ? (value as string[]) : [])
    : (value ? [value as string] : [])
  if (ids.length === 0) return <span style={{ color: '#9ca3af' }}>—</span>
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
      {ids.map(id => <EntityChip key={id} id={id} />)}
    </div>
  )
}

fieldPreviewRegistry.register(['entity_select', 'entity_select_multi'], EntitySelectPreview)
