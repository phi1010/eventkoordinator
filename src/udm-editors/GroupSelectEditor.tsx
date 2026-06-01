import { useState, useEffect, useRef, useCallback } from 'react'
import { MultiSelect } from 'primereact/multiselect'
import { Dropdown } from 'primereact/dropdown'
import { udmSearchGroups } from '../apiUdm'
import type { GroupAutocompleteItem } from '../apiUdm'
import type { FieldInputProps } from './types'
import { fieldEditorRegistry } from './registry'

type GroupOption = { label: string; value: number }

function GroupSelectEditor({ fd, value, onChange, disabled }: FieldInputProps) {
  const multi = fd.data_type === 'group_select_multi'
  const [options, setOptions] = useState<GroupOption[]>([])
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const currentIds: number[] = multi
    ? (Array.isArray(value) ? value as number[] : [])
    : (value != null ? [value as number] : [])

  const mergeGroups = useCallback((groups: GroupAutocompleteItem[]) => {
    setOptions(prev => {
      const map = new Map(prev.map(o => [o.value, o.label]))
      for (const g of groups) map.set(g.id, g.name)
      return Array.from(map.entries()).map(([v, l]) => ({ value: v, label: l }))
    })
  }, [])

  useEffect(() => {
    if (currentIds.length === 0) return
    udmSearchGroups('').then(mergeGroups).catch(() => {})
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentIds.join(',')])

  function handleFilter(e: { filter: string }) {
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => {
      udmSearchGroups(e.filter).then(mergeGroups).catch(() => {})
    }, 300)
  }

  if (multi) {
    return (
      <MultiSelect
        options={options}
        value={currentIds}
        onChange={e => onChange(e.value as number[])}
        onFilter={handleFilter}
        filter
        display="chip"
        disabled={disabled}
        placeholder="Search groups…"
        style={{ width: '100%' }}
      />
    )
  }

  return (
    <Dropdown
      options={options}
      value={(value as number) ?? null}
      onChange={e => onChange((e.value as number) ?? null)}
      onFilter={handleFilter}
      filter
      showClear
      disabled={disabled}
      placeholder="Search groups…"
      style={{ width: '100%' }}
    />
  )
}

fieldEditorRegistry.register(['group_select', 'group_select_multi'], GroupSelectEditor)
