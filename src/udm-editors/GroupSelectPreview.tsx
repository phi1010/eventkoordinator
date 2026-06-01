import { useState, useEffect } from 'react'
import { Chip } from 'primereact/chip'
import { udmSearchGroups } from '../apiUdm'
import type { GroupAutocompleteItem } from '../apiUdm'
import type { PreviewProps } from './FieldPreview'
import { fieldPreviewRegistry } from './registry-preview'

function GroupSelectPreview({ fd, value }: PreviewProps) {
  const multi = fd.data_type === 'group_select_multi'
  const ids: number[] = multi
    ? (Array.isArray(value) ? (value as number[]) : [])
    : (value != null ? [value as number] : [])

  const [nameMap, setNameMap] = useState<Map<number, string>>(new Map())

  useEffect(() => {
    if (ids.length === 0) return
    udmSearchGroups('').then((groups: GroupAutocompleteItem[]) => {
      setNameMap(new Map(groups.map(g => [g.id, g.name])))
    }).catch(() => {})
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ids.join(',')])

  if (ids.length === 0) return <span style={{ color: '#9ca3af' }}>—</span>

  const labels = ids.map(id => nameMap.get(id) ?? String(id))

  if (!multi) return <span style={{ fontSize: '0.9rem', color: '#374151' }}>{labels[0]}</span>

  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
      {labels.map((label, i) => <Chip key={ids[i]} label={label} style={{ fontSize: '0.82rem' }} />)}
    </div>
  )
}

fieldPreviewRegistry.register(['group_select', 'group_select_multi'], GroupSelectPreview)
