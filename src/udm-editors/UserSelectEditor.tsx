import { useState, useEffect, useRef, useCallback } from 'react'
import { MultiSelect } from 'primereact/multiselect'
import { Dropdown } from 'primereact/dropdown'
import { udmSearchUsers } from '../apiUdm'
import type { UserAutocompleteItem } from '../apiUdm'
import type { FieldInputProps } from './types'
import { fieldEditorRegistry } from './registry'

type UserOption = { label: string; value: string }

function UserSelectEditor({ fd, value, onChange, disabled }: FieldInputProps) {
  const multi = fd.data_type === 'user_select_multi'
  const groupIds = (fd.type_config as Record<string, unknown>)['limit_to_group_ids']
  const groupIdsStr = Array.isArray(groupIds) ? (groupIds as number[]).join(',') : undefined
  const [options, setOptions] = useState<UserOption[]>([])
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const currentIds: string[] = multi
    ? (Array.isArray(value) ? value as string[] : [])
    : (value ? [value as string] : [])

  const mergeUsers = useCallback((users: UserAutocompleteItem[]) => {
    setOptions(prev => {
      const map = new Map(prev.map(o => [o.value, o.label]))
      for (const u of users) map.set(u.id, u.display_name)
      return Array.from(map.entries()).map(([v, l]) => ({ value: v, label: l }))
    })
  }, [])

  useEffect(() => {
    if (currentIds.length === 0) return
    udmSearchUsers('', groupIdsStr).then(mergeUsers).catch(() => {})
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentIds.join(',')])

  function handleFilter(e: { filter: string }) {
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => {
      udmSearchUsers(e.filter, groupIdsStr).then(mergeUsers).catch(() => {})
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
        placeholder="Search users…"
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
      placeholder="Search users…"
      style={{ width: '100%' }}
    />
  )
}

fieldEditorRegistry.register(['user_select', 'user_select_multi'], UserSelectEditor)
