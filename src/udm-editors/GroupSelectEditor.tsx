import { useState, useEffect, useId } from 'react'
import { udmSearchGroups } from '../apiUdm'
import type { GroupAutocompleteItem } from '../apiUdm'
import type { FieldInputProps } from './types'
import { useAutocomplete } from './types'
import { fieldEditorRegistry } from './registry'
import styles from '../UdmEntityEditor.module.css'

function GroupSelectEditor({ fd, value, onChange, disabled }: FieldInputProps) {
  const multi = fd.data_type === 'group_select_multi'
  const ac = useAutocomplete<GroupAutocompleteItem>(udmSearchGroups)
  const [highlightedIndex, setHighlightedIndex] = useState(-1)
  const [nameMap, setNameMap] = useState<Record<number, string>>({})
  const listboxId = useId()

  const currentIds: number[] = multi
    ? (Array.isArray(value) ? value as number[] : [])
    : (value != null ? [value as number] : [])

  // Populate nameMap from search results as they arrive
  useEffect(() => {
    if (ac.results.length === 0) return
    setNameMap(prev => {
      const next = { ...prev }
      for (const g of ac.results) next[g.id] = g.name
      return next
    })
  }, [ac.results])

  // Fetch names for any selected IDs not yet in the nameMap
  useEffect(() => {
    const missing = currentIds.filter(id => !(id in nameMap))
    if (missing.length === 0) return
    udmSearchGroups('').then(groups => {
      setNameMap(prev => {
        const next = { ...prev }
        for (const g of groups) next[g.id] = g.name
        return next
      })
    }).catch(() => {})
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentIds.join(',')])

  // Reset highlight when results change
  useEffect(() => { setHighlightedIndex(-1) }, [ac.results])

  const filteredResults = ac.results.filter(g => !currentIds.includes(g.id))

  function selectItem(item: GroupAutocompleteItem) {
    setNameMap(prev => ({ ...prev, [item.id]: item.name }))
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

  function removeItem(id: number) {
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
          placeholder="Search groups…"
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
          {filteredResults.map((g, index) => (
            <li
              key={g.id}
              id={`${listboxId}-${index}`}
              role="option"
              aria-selected={index === highlightedIndex}
              className={`${styles.autocompleteItem}${index === highlightedIndex ? ` ${styles.autocompleteItemHighlighted}` : ''}`}
              onMouseDown={() => selectItem(g)}
              onMouseEnter={() => setHighlightedIndex(index)}
            >
              {g.name}
            </li>
          ))}
        </ul>
      )}
      <div className={styles.selectedTags}>
        {currentIds.map(id => (
          <span key={id} className={styles.selectedTag}>
            {nameMap[id] ?? String(id)}
            {!disabled && (
              <button type="button" className={styles.removeTag} onClick={() => removeItem(id)}>×</button>
            )}
          </span>
        ))}
      </div>
    </div>
  )
}

fieldEditorRegistry.register(['group_select', 'group_select_multi'], GroupSelectEditor)
