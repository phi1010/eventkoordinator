import { useState, useEffect, useCallback, useId } from 'react'
import { udmSearchEntities } from '../apiUdm'
import type { EntityAutocompleteItem } from '../apiUdm'
import type { FieldInputProps } from './types'
import { useAutocomplete } from './types'
import { fieldEditorRegistry } from './registry'
import styles from '../UdmEntityEditor.module.css'

function EntitySelectEditor({ fd, value, onChange, disabled }: FieldInputProps) {
  const multi = fd.data_type === 'entity_select_multi'
  const typeIds = (fd.type_config as Record<string, unknown>)['limit_to_type_ids']
  const typeIdsStr = Array.isArray(typeIds) ? (typeIds as string[]).join(',') : undefined
  const fetcher = useCallback((q: string) => udmSearchEntities(q, typeIdsStr), [typeIdsStr])
  const ac = useAutocomplete<EntityAutocompleteItem>(fetcher)
  const [highlightedIndex, setHighlightedIndex] = useState(-1)
  const [displayMap, setDisplayMap] = useState<Record<string, string>>({})
  const listboxId = useId()

  const currentIds: string[] = multi
    ? (Array.isArray(value) ? value as string[] : [])
    : (value ? [value as string] : [])

  // Persist display strings from search results
  useEffect(() => {
    if (ac.results.length === 0) return
    setDisplayMap(prev => {
      const next = { ...prev }
      for (const e of ac.results) next[e.id] = e.display ?? e.id
      return next
    })
  }, [ac.results])

  // Fetch display strings for pre-selected IDs not yet in the map
  useEffect(() => {
    const missing = currentIds.filter(id => !(id in displayMap))
    if (missing.length === 0) return
    udmSearchEntities('', typeIdsStr, missing.join(',')).then(items => {
      setDisplayMap(prev => {
        const next = { ...prev }
        for (const e of items) next[e.id] = e.display ?? e.id
        return next
      })
    }).catch(() => {})
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentIds.join(',')])

  useEffect(() => { setHighlightedIndex(-1) }, [ac.results])

  const filteredResults = ac.results.filter(e => !currentIds.includes(e.id))

  function selectItem(item: EntityAutocompleteItem) {
    setDisplayMap(prev => ({ ...prev, [item.id]: item.display ?? item.id }))
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
          placeholder="Search entities…"
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
          {filteredResults.map((e, index) => (
            <li
              key={e.id}
              id={`${listboxId}-${index}`}
              role="option"
              aria-selected={index === highlightedIndex}
              className={`${styles.autocompleteItem}${index === highlightedIndex ? ` ${styles.autocompleteItemHighlighted}` : ''}`}
              onMouseDown={() => selectItem(e)}
              onMouseEnter={() => setHighlightedIndex(index)}
            >
              {e.display ?? e.id}
            </li>
          ))}
        </ul>
      )}
      <div className={styles.selectedTags}>
        {currentIds.map(id => (
          <span key={id} className={styles.selectedTag}>
            {displayMap[id] ?? id}
            {!disabled && (
              <button type="button" className={styles.removeTag} onClick={() => removeItem(id)}>×</button>
            )}
          </span>
        ))}
      </div>
    </div>
  )
}

fieldEditorRegistry.register(['entity_select', 'entity_select_multi'], EntitySelectEditor)
