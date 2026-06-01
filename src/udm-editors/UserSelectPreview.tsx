import type { PreviewProps } from './FieldPreview'
import { fieldPreviewRegistry } from './registry-preview'

function UserChip({ id }: { id: string }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 8px', borderRadius: '999px', fontSize: '0.82rem', background: '#f0fdf4', color: '#166534', border: '1px solid #bbf7d0', fontFamily: 'monospace' }}>
      👤 {id}
    </span>
  )
}

function UserSelectPreview({ fd, value }: PreviewProps) {
  const multi = fd.data_type === 'user_select_multi'
  const ids: string[] = multi
    ? (Array.isArray(value) ? (value as string[]) : [])
    : (value ? [value as string] : [])
  if (ids.length === 0) return <span style={{ color: '#9ca3af' }}>—</span>
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
      {ids.map(id => <UserChip key={id} id={id} />)}
    </div>
  )
}

fieldPreviewRegistry.register(['user_select', 'user_select_multi'], UserSelectPreview)
