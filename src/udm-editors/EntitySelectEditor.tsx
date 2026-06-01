import { useState, useEffect, useRef, useCallback } from 'react'
import { MultiSelect } from 'primereact/multiselect'
import { Dropdown } from 'primereact/dropdown'
import { udmSearchEntities } from '../apiUdm'
import type { EntityAutocompleteItem } from '../apiUdm'
import type { FieldInputProps } from './types'
import { fieldEditorRegistry } from './registry'

type EntityOption = { label: string; value: string }

function EntitySelectEditor({ fd, value, onChange, disabled }: FieldInputProps) {
  const multi = fd.data_type === 'entity_select_multi'
  const typeIds = (fd.type_config as Record<string, unknown>)['limit_to_type_ids']
  const typeIdsStr = Array.isArray(typeIds) ? (typeIds as string[]).join(',') : undefined
  const [options, setOptions] = useState<EntityOption[]>([])
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const currentIds: string[] = multi
    ? (Array.isArray(value) ? value as string[] : [])
    : (value ? [value as string] : [])

  const mergeEntities = useCallback((entities: EntityAutocompleteItem[]) => {
    setOptions(prev => {
      const map = new Map(prev.map(o => [o.value, o.label]))
      for (const e of entities) map.set(e.id, e.display ?? e.id)
      return Array.from(map.entries()).map(([v, l]) => ({ value: v, label: l }))
    })
  }, [])

  useEffect(() => {
    if (currentIds.length === 0) return
    udmSearchEntities('', typeIdsStr, currentIds.join(',')).then(mergeEntities).catch(() => {})
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentIds.join(',')])

  function handleFilter(e: { filter: string }) {
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => {
      udmSearchEntities(e.filter, typeIdsStr).then(mergeEntities).catch(() => {})
    }, 300)
  }

  if (multi) {
    return (
      <MultiSelect
        options={options}
        value={currentIds}
        onChange={e => onChange(e.value as string[])}
        onFilter={handleFilter}
        filter
        display="chip"
        disabled={disabled}
        placeholder="Search entities…"
        style={{ width: '100%' }}
      />
    )
  }

  return (
    <Dropdown
      options={options}
      value={(value as string) || null}
      onChange={e => onChange((e.value as string) || null)}
      onFilter={handleFilter}
      filter
      showClear
      disabled={disabled}
      placeholder="Search entities…"
      style={{ width: '100%' }}
    />
  )
}

fieldEditorRegistry.register(['entity_select', 'entity_select_multi'], EntitySelectEditor)
