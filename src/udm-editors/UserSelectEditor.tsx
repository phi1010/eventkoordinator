import { useState, useEffect, useCallback, useId } from 'react'
import { udmSearchUsers } from '../apiUdm'
import type { UserAutocompleteItem } from '../apiUdm'
import type { FieldInputProps } from './types'
import { useAutocomplete } from './types'
import { fieldEditorRegistry } from './registry'
import styles from '../UdmEntityEditor.module.css'

function UserSelectEditor({ fd, value, onChange, disabled }: FieldInputProps) {
  const multi = fd.data_type === 'user_select_multi'
  const groupIds = (fd.type_config as Record<string, unknown>)['limit_to_group_ids']
  const groupIdsStr = Array.isArray(groupIds) ? (groupIds as number[]).join(',') : undefined
  const fetcher = useCallback((q: string) => udmSearchUsers(q, groupIdsStr), [groupIdsStr])
  const ac = useAutocomplete<UserAutocompleteItem>(fetcher)
  const [highlightedIndex, setHighlightedIndex] = useState(-1)
  const [nameMap, setNameMap] = useState<Record<string, string>>({})
  const listboxId = useId()

  const currentIds: string[] = multi
    ? (Array.isArray(value) ? value as string[] : [])
    : (value ? [value as string] : [])

  // Persist display names from search results
  useEffect(() => {
    if (ac.results.length === 0) return
    setNameMap(prev => {
      const next = { ...prev }
      for (const u of ac.results) next[u.id] = u.display_name
      return next
    })
  }, [ac.results])

  // Fetch display names for pre-selected IDs not yet in the map
  useEffect(() => {
    const missing = currentIds.filter(id => !(id in nameMap))
    if (missing.length === 0) return
    udmSearchUsers('', groupIdsStr).then(users => {
      setNameMap(prev => {
        const next = { ...prev }
        for (const u of users) next[u.id] = u.display_name
        return next
      })
    }).catch(() => {})
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentIds.join(',')])

  // Reset highlight when results change
  useEffect(() => { setHighlightedIndex(-1) }, [ac.results])

  const filteredResults = ac.results.filter(u => !currentIds.includes(u.id))

  function selectItem(item: UserAutocompleteItem) {
    setNameMap(prev => ({ ...prev, [item.id]: item.display_name }))
    if (multi) {
      if (!currentIds.includes(item.id)) onChange([...currentIds, item.id])
    } else {
      onChange(item.id)
    }
    ac.setQuery('')
    ac.setResults([])
    ac.setOpen(false)
    setHighlightedIndex(-1)
  }

  function removeItem(id: string) {
    if (multi) onChange(currentIds.filter(x => x !== id))
    else onChange(null)
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlightedIndex(prev => Math.min(prev + 1, filteredResults.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlightedIndex(prev => Math.max(prev - 1, -1))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (highlightedIndex >= 0 && filteredResults[highlightedIndex]) {
        selectItem(filteredResults[highlightedIndex])
      } else if (filteredResults.length === 1) {
        selectItem(filteredResults[0])
      }
    } else if (e.key === 'Escape') {
      ac.setOpen(false)
      setHighlightedIndex(-1)
    }
  }

  const isOpen = ac.open && filteredResults.length > 0

  return (
    <div className={styles.autocompleteWrapper}>
      {!disabled && (
        <input
          className={styles.input}
          value={ac.query}
          onChange={e => ac.search(e.target.value)}
          onBlur={() => setTimeout(() => { ac.setOpen(false); setHighlightedIndex(-1) }, 150)}
          onKeyDown={handleKeyDown}
          placeholder="Search users…"
          disabled={disabled}
          role="combobox"
          aria-expanded={isOpen}
          aria-controls={listboxId}
          aria-autocomplete="list"
          aria-activedescendant={highlightedIndex >= 0 ? `${listboxId}-${highlightedIndex}` : undefined}
        />
      )}
      {isOpen && (
        <ul
          id={listboxId}
          role="listbox"
          className={styles.autocompleteDropdown}
          style={{ listStyle: 'none', margin: 0, padding: 0 }}
        >
          {filteredResults.map((u, index) => (
            <li
              key={u.id}
              id={`${listboxId}-${index}`}
              role="option"
              aria-selected={index === highlightedIndex}
              className={`${styles.autocompleteItem}${index === highlightedIndex ? ` ${styles.autocompleteItemHighlighted}` : ''}`}
              onMouseDown={() => selectItem(u)}
              onMouseEnter={() => setHighlightedIndex(index)}
            >
              {u.display_name}
            </li>
          ))}
        </ul>
      )}
      <div className={styles.selectedTags}>
        {currentIds.map(id => (
          <span key={id} className={styles.selectedTag}>
            {nameMap[id] ?? id}
            {!disabled && (
              <button type="button" className={styles.removeTag} onClick={() => removeItem(id)}>×</button>
            )}
          </span>
        ))}
      </div>
    </div>
  )
}

fieldEditorRegistry.register(['user_select', 'user_select_multi'], UserSelectEditor)
