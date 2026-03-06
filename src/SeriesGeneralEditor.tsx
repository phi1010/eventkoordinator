import { useState, useEffect } from 'react'
import { updateSeries, type Series } from './api'
import { useUnsavedChanges } from './useUnsavedChanges'
import styles from './EventGeneralEditor.module.css'

interface SeriesGeneralEditorProps {
  series: Series
  onSeriesUpdate: (updated: Series) => void
  onRequestNavigation?: (confirmFn: () => Promise<boolean>) => void
  disabled?: boolean
}

export function SeriesGeneralEditor({ series, onSeriesUpdate, onRequestNavigation, disabled = false }: SeriesGeneralEditorProps) {
  const [name, setName] = useState(series.name)
  const [description, setDescription] = useState(series.description || '')
  const [changedFields, setChangedFields] = useState<Set<string>>(new Set())
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Track unsaved changes
  const hasChanges = changedFields.size > 0
  const { confirmNavigation } = useUnsavedChanges(hasChanges)

  // Expose confirmation function to parent
  useEffect(() => {
    if (onRequestNavigation) {
      onRequestNavigation(confirmNavigation)
    }
  }, [onRequestNavigation, confirmNavigation])

  // Reset form state when series changes
  useEffect(() => {
    setName(series.name)
    setDescription(series.description || '')
    setChangedFields(new Set())
    setError(null)
  }, [series.id, series.name, series.description])

  const handleNameChange = (value: string) => {
    setName(value)
    setChangedFields((prev) => new Set(prev).add('name'))
    setError(null)
  }

  const handleDescriptionChange = (value: string) => {
    setDescription(value)
    setChangedFields((prev) => new Set(prev).add('description'))
    setError(null)
  }

  const handleSave = async () => {
    try {
      setIsSaving(true)
      setError(null)

      const updates: Record<string, string | undefined> = {}
      if (changedFields.has('name') && name !== series.name) {
        updates.name = name
      }
      if (changedFields.has('description') && description !== series.description) {
        updates.description = description
      }

      if (Object.keys(updates).length === 0) {
        setChangedFields(new Set())
        return
      }

      const updated = await updateSeries({
        seriesId: series.id,
        ...updates,
      })

      onSeriesUpdate(updated)
      setChangedFields(new Set())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save series')
    } finally {
      setIsSaving(false)
    }
  }

  const handleCancel = () => {
    setName(series.name)
    setDescription(series.description || '')
    setChangedFields(new Set())
    setError(null)
  }

  return (
    <div className={styles.container}>
      <form className={styles.form} aria-label="Edit series">
        <div className={styles.formGroup}>
          <label htmlFor="series-name" className={styles.label}>
            Series Name
            {changedFields.has('name') && <span className={styles.changedIndicator} aria-label="unsaved change">●</span>}
          </label>
          <input
            id="series-name"
            type="text"
            value={name}
            onChange={(e) => handleNameChange(e.target.value)}
            className={`${styles.input} ${changedFields.has('name') ? styles.changed : ''}`}
            disabled={isSaving || disabled}
          />
        </div>

        <div className={styles.formGroup}>
          <label htmlFor="series-description" className={styles.label}>
            Description
            {changedFields.has('description') && <span className={styles.changedIndicator} aria-label="unsaved change">●</span>}
          </label>
          <textarea
            id="series-description"
            value={description}
            onChange={(e) => handleDescriptionChange(e.target.value)}
            className={`${styles.textarea} ${changedFields.has('description') ? styles.changed : ''}`}
            rows={4}
            disabled={isSaving || disabled}
          />
        </div>

        {error && <div className={styles.error} role="alert">{error}</div>}

        <div className={styles.buttonGroup}>
          <button
            type="button"
            onClick={handleSave}
            disabled={!hasChanges || isSaving}
            className={styles.saveButton}
            aria-busy={isSaving}
          >
            {isSaving ? 'Saving...' : 'Save Changes'}
          </button>
          {hasChanges && (
            <button
              type="button"
              onClick={handleCancel}
              disabled={isSaving || disabled}
              className={styles.cancelButton}
            >
              Cancel
            </button>
          )}
        </div>
      </form>
    </div>
  )
}
