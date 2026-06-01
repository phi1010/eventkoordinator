import type { PreviewProps } from './FieldPreview'
import { fieldPreviewRegistry } from './registry-preview'

function GroupChip({ id }: { id: number | string }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 8px', borderRadius: '999px', fontSize: '0.82rem', background: '#fefce8', color: '#713f12', border: '1px solid #fef08a' }}>
      # {id}
    </span>
  )
}

function GroupSelectPreview({ fd, value }: PreviewProps) {
  const multi = fd.data_type === 'group_select_multi'
  const ids: (number | string)[] = multi
    ? (Array.isArray(value) ? (value as (number | string)[]) : [])
    : (value != null ? [value as number | string] : [])
  if (ids.length === 0) return <span style={{ color: '#9ca3af' }}>—</span>
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
      {ids.map(id => <GroupChip key={String(id)} id={id} />)}
    </div>
  )
}

fieldPreviewRegistry.register(['group_select', 'group_select_multi'], GroupSelectPreview)
