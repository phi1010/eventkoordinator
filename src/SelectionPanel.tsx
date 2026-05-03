import {useEffect, useRef, useState} from 'react'
import {useTranslation} from 'react-i18next'
import styles from './SelectionPanel.module.css'

export interface SelectionItem {
  id: string
  [key: string]: unknown
}

export interface SelectionPanelProps<T extends SelectionItem> {
  items: T[]
  selectedItemId: string
  onSelectionChange: (itemId: string) => void
  onBeforeSelectionChange?: (newItemId: string) => Promise<boolean>
  renderItemLabel: (item: T) => React.ReactNode
  renderContent: (selectedItem: T) => React.ReactNode
  sidebarTitle: string
  belowTitleElement?: React.ReactElement
  isNested?: boolean
}

export function SelectionPanel<T extends SelectionItem>({
  items,
  selectedItemId,
  onSelectionChange,
  onBeforeSelectionChange,
  renderItemLabel,
  renderContent,
  sidebarTitle,
  belowTitleElement,
  isNested = false,
}: SelectionPanelProps<T>) {
  const { t } = useTranslation()
  const [comboboxOpen, setComboboxOpen] = useState(false)
  const selectedItem = items.find((item) => item.id === selectedItemId)
  const itemListRef = useRef<HTMLUListElement>(null)
  const activeItemRef = useRef<HTMLLIElement>(null)
  const listboxId = `combobox-list-${sidebarTitle.replace(/\s+/g, '-').toLowerCase()}`

  // Scroll to active item when selection changes
  useEffect(() => {
    if (activeItemRef.current && itemListRef.current) {
      // Use setTimeout to ensure the DOM has updated
      setTimeout(() => {
        activeItemRef.current?.scrollIntoView({
          behavior: 'smooth',
          block: 'nearest',
        })
      }, 100)
    }
  }, [selectedItemId])

  const handleSelectionChange = async (itemId: string) => {
    if (itemId === selectedItemId) {
      return
    }

    if (onBeforeSelectionChange) {
      const confirmed = await onBeforeSelectionChange(itemId)
      if (!confirmed) {
        return
      }
    }

    onSelectionChange(itemId)
  }

  if (!selectedItem) return null

  const containerClass = isNested ? styles.nestedContainer : styles.selectorContainer
  const sidebarClass = isNested ? styles.nestedSidebar : styles.sidebar
  const comboboxWrapperClass = isNested ? styles.nestedComboboxWrapper : styles.comboboxWrapper

  return (
    <div className={containerClass}>
      {/* Sidebar - visible on wide screens */}
      <aside className={sidebarClass} aria-label={sidebarTitle}>
        <h2>{sidebarTitle}</h2>
        {belowTitleElement && (
          <div className={styles.belowTitleElement}>
            {belowTitleElement}
          </div>
        )}
        <ul className={styles.itemList} role="listbox" aria-label={sidebarTitle} ref={itemListRef}>
          {items.map((item) => (
            <li
              key={item.id}
              ref={selectedItem.id === item.id ? activeItemRef : null}
              className={`${styles.item} ${selectedItem.id === item.id ? styles.active : ''}`}
              onClick={() => void handleSelectionChange(item.id)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  void handleSelectionChange(item.id)
                }
              }}
              tabIndex={0}
              role="option"
              aria-selected={selectedItem.id === item.id}
            >
              {renderItemLabel(item)}
            </li>
          ))}
        </ul>
      </aside>

      {/* Combobox - visible on narrow screens */}
      <div className={comboboxWrapperClass}>
        <div className={styles.comboboxContainer}>
          <button
            className={styles.comboboxButton}
            onClick={() => setComboboxOpen(!comboboxOpen)}
            aria-expanded={comboboxOpen}
            aria-haspopup="listbox"
            aria-controls={listboxId}
            aria-label={t('selection.select', { title: sidebarTitle })}
          >
            <span className={styles.comboboxValue}>{renderItemLabel(selectedItem)}</span>
            <span className={styles.comboboxIcon} aria-hidden="true">▼</span>
          </button>

          {comboboxOpen && (
            <ul className={styles.comboboxList} role="listbox" id={listboxId} aria-label={sidebarTitle}>
              {items.map((item) => (
                <li
                  key={item.id}
                  className={`${styles.comboboxItem} ${selectedItem.id === item.id ? styles.active : ''}`}
                  onClick={() => {
                    void handleSelectionChange(item.id)
                    setComboboxOpen(false)
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      void handleSelectionChange(item.id)
                      setComboboxOpen(false)
                    }
                  }}
                  role="option"
                  aria-selected={selectedItem.id === item.id}
                  tabIndex={0}
                >
                  {renderItemLabel(item)}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Main content area */}
      <main className={styles.content} aria-label={`${sidebarTitle} content`}>
        {renderContent(selectedItem)}
      </main>
    </div>
  )
}



