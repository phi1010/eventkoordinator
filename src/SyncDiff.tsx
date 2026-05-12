import { useState, useEffect, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { DiffView, DiffModeEnum } from '@git-diff-view/react'
import { generateDiffFile } from '@git-diff-view/file'
import '@git-diff-view/react/styles/diff-view.css'
import { fetchSyncDiff, type PropertyDiff } from './api'
import { SelectionPanel, type SelectionItem } from './SelectionPanel'
import styles from './SyncDiff.module.css'

interface PropertyItem extends SelectionItem {
  property_name: string
  local_value: string
  remote_value: string
  file_type: string
}

export function SyncDiff() {
  const { t } = useTranslation()
  const { seriesId, eventId, targetId } = useParams<{
    seriesId: string
    eventId: string
    targetId: string
  }>()
  const navigate = useNavigate()
  const [properties, setProperties] = useState<PropertyDiff[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedPropertyId, setSelectedPropertyId] = useState<string>('')
  const [diffMode, setDiffMode] = useState<DiffModeEnum>(DiffModeEnum.Split)
  const [isNarrowScreen, setIsNarrowScreen] = useState(window.innerWidth < 768)

  // Handle window resize for responsive behavior
  useEffect(() => {
    const handleResize = () => {
      const narrow = window.innerWidth < 768
      setIsNarrowScreen(narrow)

      // Force unified view on narrow screens
      if (narrow && diffMode === DiffModeEnum.Split) {
        setDiffMode(DiffModeEnum.Unified)
      }
    }

    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [diffMode])

  useEffect(() => {
    const loadDiffData = async () => {
      if (!seriesId || !eventId || !targetId) {
        setError(t('syncDiff.missingParams'))
        setLoading(false)
        return
      }

      try {
        setLoading(true)
        const data = await fetchSyncDiff(seriesId, eventId, targetId)
        setProperties(data.properties)
        if (data.properties.length > 0) {
          setSelectedPropertyId(`prop-0`)
        }
        setError(null)
      } catch (err) {
        setError(err instanceof Error ? err.message : t('syncDiff.failedLoad'))
      } finally {
        setLoading(false)
      }
    }

    loadDiffData()
  }, [seriesId, eventId, targetId])

  // Convert properties to SelectionItems
  const propertyItems: PropertyItem[] = properties.map((prop, index) => ({
    id: `prop-${index}`,
    property_name: prop.property_name,
    local_value: prop.local_value,
    remote_value: prop.remote_value,
    file_type: prop.file_type,
  }))

  const selectedProperty = propertyItems.find(p => p.id === selectedPropertyId)

  const diffFile = useMemo(() => {
    if (!selectedProperty) {
      return null
    }

    const instance = generateDiffFile(
      `local/${selectedProperty.property_name}`,
      selectedProperty.local_value,
      `remote/${selectedProperty.property_name}`,
      selectedProperty.remote_value,
      selectedProperty.file_type,
      selectedProperty.file_type,
      { context: Number.MAX_SAFE_INTEGER },
    )
    instance.initRaw()
    return instance
  }, [selectedProperty])

  // Helper to check if property has differences and count changes
  const getPropertyDiffStats = (prop: PropertyItem) => {
    if (prop.local_value === prop.remote_value) {
      return { hasDiff: false, additions: 0, deletions: 0 }
    }

    // Simple line-based diff counting
    const localLines = prop.local_value.split('\n')
    const remoteLines = prop.remote_value.split('\n')

    let additions = 0
    let deletions = 0

    // Count lines that are different (simplified)
    const maxLines = Math.max(localLines.length, remoteLines.length)
    for (let i = 0; i < maxLines; i++) {
      const localLine = localLines[i] || ''
      const remoteLine = remoteLines[i] || ''

      if (localLine !== remoteLine) {
        if (i >= localLines.length) {
          additions++
        } else if (i >= remoteLines.length) {
          deletions++
        } else {
          additions++
          deletions++
        }
      }
    }

    return { hasDiff: true, additions, deletions }
  }

  const renderPropertyLabel = (prop: PropertyItem) => {
    const diffStats = getPropertyDiffStats(prop)
    return (
      <div className={styles.propertyLabelWrapper}>
        <div className={styles.propertyInfo}>
          <span className={styles.propertyName}>{prop.property_name}</span>
          {diffStats.hasDiff && (
            <div className={styles.diffBadge}>
              {diffStats.additions > 0 && (
                <span className={styles.additions}>+{diffStats.additions}</span>
              )}
              {diffStats.deletions > 0 && (
                <span className={styles.deletions}>-{diffStats.deletions}</span>
              )}
            </div>
          )}
        </div>
        <span className={styles.propertyType}>.{prop.file_type}</span>
      </div>
    )
  }

  if (loading) {
    return (
      <div className={styles.container}>
        <div className={styles.loading}>{t('syncDiff.loading')}</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className={styles.container}>
        <div className={styles.error}>
          <h2>{t('common.error')}</h2>
          <p>{error}</p>
          <button
            type="button"
            onClick={() => navigate(-1)}
            className={styles.backButton}
            aria-label={t('common.back')}
          >
            {t('common.back')}
          </button>
        </div>
      </div>
    )
  }

  if (properties.length === 0) {
    return (
      <div className={styles.container}>
        <div className={styles.empty}>
          <h2>{t('syncDiff.noDifferences')}</h2>
          <p>{t('syncDiff.inSync')}</p>
          <button
            type="button"
            onClick={() => navigate(-1)}
            className={styles.backButton}
            aria-label={t('common.back')}
          >
            {t('common.back')}
          </button>
        </div>
      </div>
    )
  }

  const renderDiffContent = () => (
    <div className={styles.diffViewerContainer}>
      <div className={styles.diffHeader}>
        <div className={styles.headerTop}>
          <button
            type="button"
            onClick={() => navigate(-1)}
            className={styles.backButton}
              aria-label={t('common.back')}
          >
            ← {t('common.back')}
          </button>
          <h1>{t('syncDiff.title')}</h1>
          {!isNarrowScreen && (
            <div className={styles.modeToggle} role="group" aria-label={t('syncDiff.modeToggle')}>
              <button
                type="button"
                className={diffMode === DiffModeEnum.Split ? styles.active : ''}
                onClick={() => setDiffMode(DiffModeEnum.Split)}
                aria-pressed={diffMode === DiffModeEnum.Split}
                aria-label={t('syncDiff.splitView')}
              >
                {t('syncDiff.split')}
              </button>
              <button
                type="button"
                className={diffMode === DiffModeEnum.Unified ? styles.active : ''}
                onClick={() => setDiffMode(DiffModeEnum.Unified)}
                aria-pressed={diffMode === DiffModeEnum.Unified}
                aria-label={t('syncDiff.unifiedView')}
              >
                {t('syncDiff.unified')}
              </button>
            </div>
          )}
        </div>
        <div className={styles.metadata}>
          <span className={styles.metaItem}>
            <strong>Series:</strong> {seriesId}
          </span>
          <span className={styles.metaItem}>
            <strong>Event:</strong> {eventId}
          </span>
          <span className={styles.metaItem}>
            <strong>Target:</strong> {targetId}
          </span>
        </div>
      </div>
      <div className={styles.diffViewer}>
        {selectedProperty && selectedProperty.local_value === selectedProperty.remote_value ? (
          <pre className={styles.unchangedContent}>{selectedProperty.local_value}</pre>
        ) : (
          diffFile && (
            <DiffView
              diffFile={diffFile}
              diffViewWrap={false}
              diffViewAddWidget
              renderWidgetLine={({ onClose }) => (
                <div className={styles.widget}>
                  <span>Additional context can be added here</span>
                  <button type="button" className={styles.widgetButton} onClick={onClose}>
                    Close
                  </button>
                </div>
              )}
              diffViewTheme="light"
              diffViewHighlight={true}
              diffViewMode={diffMode}
            />
          )
        )}
      </div>
    </div>
  )

  return (
    <SelectionPanel<PropertyItem>
      items={propertyItems}
      selectedItemId={selectedPropertyId}
      onSelectionChange={setSelectedPropertyId}
      renderItemLabel={renderPropertyLabel}
      renderContent={renderDiffContent}
      sidebarTitle={`${t('syncDiff.properties')} (${properties.length})`}
      isNested={false}
    />
  )
}

