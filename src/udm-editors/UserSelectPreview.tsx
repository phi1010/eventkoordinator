import { useState, useEffect } from 'react'
import { Chip } from 'primereact/chip'
import { udmSearchUsers } from '../apiUdm'
import type { UserAutocompleteItem } from '../apiUdm'
import type { PreviewProps } from './FieldPreview'
import { fieldPreviewRegistry } from './registry-preview'

function UserSelectPreview({ fd, value }: PreviewProps) {
  const multi = fd.data_type === 'user_select_multi'
  const ids: string[] = multi
    ? (Array.isArray(value) ? (value as string[]) : [])
    : (value ? [value as string] : [])

  const [nameMap, setNameMap] = useState<Map<string, string>>(new Map())

  useEffect(() => {
    if (ids.length === 0) return
    const groupIds = ((fd.type_config as Record<string, unknown>)?.['limit_to_group_ids'] as number[] | undefined)
    const groupStr = groupIds?.join(',')
    udmSearchUsers('', groupStr).then((users: UserAutocompleteItem[]) => {
      setNameMap(new Map(users.map(u => [u.id, u.display_name])))
    }).catch(() => {})
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ids.join(',')])

  if (ids.length === 0) return <span style={{ color: '#9ca3af' }}>—</span>

  const labels = ids.map(id => nameMap.get(id) ?? id)

  if (!multi) return <span style={{ fontSize: '0.9rem', color: '#374151' }}>{labels[0]}</span>

  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
      {labels.map((label, i) => <Chip key={ids[i]} label={label} style={{ fontSize: '0.82rem' }} />)}
    </div>
  )
}

fieldPreviewRegistry.register(['user_select', 'user_select_multi'], UserSelectPreview)
