import { useState, useEffect } from 'react'
import { Chip } from 'primereact/chip'
import { udmSearchEntities } from '../apiUdm'
import type { EntityAutocompleteItem } from '../apiUdm'
import type { PreviewProps } from './FieldPreview'
import { fieldPreviewRegistry } from './registry-preview'

function EntitySelectPreview({ fd, value }: PreviewProps) {
  const multi = fd.data_type === 'entity_select_multi'
  const ids: string[] = multi
    ? (Array.isArray(value) ? (value as string[]) : [])
    : (value ? [value as string] : [])

  const [displayMap, setDisplayMap] = useState<Map<string, string>>(new Map())

  useEffect(() => {
    if (ids.length === 0) return
    const typeIds = ((fd.type_config as Record<string, unknown>)?.['limit_to_type_ids'] as string[] | undefined)?.join(',')
    udmSearchEntities('', typeIds, ids.join(',')).then((entities: EntityAutocompleteItem[]) => {
      setDisplayMap(new Map(entities.map(e => [e.id, e.display])))
    }).catch(() => {})
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ids.join(',')])

  if (ids.length === 0) return <span style={{ color: '#9ca3af' }}>—</span>

  const labels = ids.map(id => displayMap.get(id) ?? id)

  if (!multi) return <span style={{ fontSize: '0.9rem', color: '#374151' }}>{labels[0]}</span>

  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
      {labels.map((label, i) => <Chip key={ids[i]} label={label} style={{ fontSize: '0.82rem' }} />)}
    </div>
  )
}

fieldPreviewRegistry.register(['entity_select', 'entity_select_multi'], EntitySelectPreview)
