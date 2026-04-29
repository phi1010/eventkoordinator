import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import {
  fetchEventTransitions,
  executeEventTransition,
  fetchEventFlowChartSvg,
  type EventTransition,
  type Event,
} from './api'
import { EventStatusBadge } from './EventStatusBadge'
import styles from './EventTransitionButtons.module.css'

interface EventTransitionButtonsProps {
  seriesId: string
  eventId: string
  currentStatus: string
  onTransitionSuccess?: (updatedEvent: Event) => void
  onTransitionError?: (error: string) => void
}

export function EventTransitionButtons({
  seriesId,
  eventId,
  currentStatus,
  onTransitionSuccess,
  onTransitionError,
}: EventTransitionButtonsProps) {
  const { t } = useTranslation()
  const [transitions, setTransitions] = useState<EventTransition[]>([])
  const [status, setStatus] = useState(currentStatus)
  const [loading, setLoading] = useState(false)
  const [executing, setExecuting] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Flow chart state
  const [flowChartOpen, setFlowChartOpen] = useState(false)
  const [flowChartSvg, setFlowChartSvg] = useState<string | null>(null)
  const [flowChartLoading, setFlowChartLoading] = useState(false)
  const [flowChartError, setFlowChartError] = useState<string | null>(null)

  const loadTransitions = async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await fetchEventTransitions(seriesId, eventId)
      setTransitions(data.transitions)
      setStatus(data.current_status)
    } catch (err) {
      setError(t('event.failedToLoadTransitions'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (seriesId && eventId) {
      void loadTransitions()
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seriesId, eventId])

  // Keep local status in sync if parent passes a new value
  useEffect(() => {
    setStatus(currentStatus)
  }, [currentStatus])

  const handleExecute = async (action: string) => {
    try {
      setExecuting(action)
      setError(null)
      const updatedEvent = await executeEventTransition(seriesId, eventId, action)
      setStatus(updatedEvent.status ?? status)
      await loadTransitions()
      onTransitionSuccess?.(updatedEvent)
    } catch (err) {
      const msg = err instanceof Error ? err.message : t('event.transitionFailedShort')
      setError(msg)
      onTransitionError?.(msg)
    } finally {
      setExecuting(null)
    }
  }

  const handleToggleFlowChart = async () => {
    const nextOpen = !flowChartOpen
    setFlowChartOpen(nextOpen)
    if (nextOpen && flowChartSvg === null && !flowChartLoading) {
      try {
        setFlowChartLoading(true)
        setFlowChartError(null)
        const svg = await fetchEventFlowChartSvg()
        setFlowChartSvg(svg)
      } catch (err) {
        setFlowChartError(err instanceof Error ? err.message : t('event.failedToLoadFlowChart'))
      } finally {
        setFlowChartLoading(false)
      }
    }
  }

  return (
    <div className={styles.section}>
      {/* Status row: badge + readonly text field */}
      <div className={styles.statusRow}>
        <span className={styles.statusLabel}>{t('event.status')}:</span>
        <EventStatusBadge status={status} />
      </div>

      {/* Error */}
      {error && (
        <div className={styles.errorBox} role="alert">
          {error}
        </div>
      )}

      {/* Transition buttons */}
      {!loading && transitions.length > 0 && (
        <div className={styles.buttonRow}>
          {transitions.map((t_item) => (
            <button
              key={t_item.action}
              className={`${styles.transitionButton} ${executing !== null && executing !== t_item.action ? styles.busy : ''}`}
              onClick={() => void handleExecute(t_item.action)}
              disabled={!t_item.enabled || executing !== null}
              title={t_item.disable_reason ?? undefined}
              aria-busy={executing === t_item.action}
            >
              {executing === t_item.action ? t('event.processing') : t_item.label}
            </button>
          ))}
        </div>
      )}

      {loading && (
        <div className={styles.flowChartLoading}>{t('event.loadingTransitions')}</div>
      )}

      {/* Flow chart toggle */}
      <button
        type="button"
        className={styles.flowChartToggle}
        onClick={() => void handleToggleFlowChart()}
        aria-expanded={flowChartOpen}
      >
        <span className={`${styles.flowChartArrow} ${flowChartOpen ? styles.open : ''}`}>▶</span>
        {t('event.lifecycleDiagram')}
      </button>

      {flowChartOpen && (
        <div className={styles.flowChartContainer} aria-label={t('event.lifecycleDiagramAria')}>
          {flowChartLoading && <p className={styles.flowChartLoading}>{t('event.loadingDiagram')}</p>}
          {flowChartError && <p className={styles.errorBox}>{flowChartError}</p>}
          {flowChartSvg && (
            // SVG is served by our own backend – safe to inject
            <div dangerouslySetInnerHTML={{ __html: flowChartSvg }} />
          )}
        </div>
      )}
    </div>
  )
}


