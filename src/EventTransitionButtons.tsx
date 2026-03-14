import { useState, useEffect } from 'react'
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
      const msg = err instanceof Error ? err.message : 'Failed to load transitions'
      setError(msg)
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
      const msg = err instanceof Error ? err.message : 'Transition failed'
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
        setFlowChartError(err instanceof Error ? err.message : 'Failed to load flow chart')
      } finally {
        setFlowChartLoading(false)
      }
    }
  }

  return (
    <div className={styles.section}>
      {/* Status row: badge + readonly text field */}
      <div className={styles.statusRow}>
        <span className={styles.statusLabel}>Status:</span>
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
          {transitions.map((t) => (
            <button
              key={t.action}
              className={`${styles.transitionButton} ${executing !== null && executing !== t.action ? styles.busy : ''}`}
              onClick={() => void handleExecute(t.action)}
              disabled={!t.enabled || executing !== null}
              title={t.disable_reason ?? undefined}
              aria-busy={executing === t.action}
            >
              {executing === t.action ? 'Processing…' : t.label}
            </button>
          ))}
        </div>
      )}

      {loading && (
        <div className={styles.flowChartLoading}>Loading transitions…</div>
      )}

      {/* Flow chart toggle */}
      <button
        type="button"
        className={styles.flowChartToggle}
        onClick={() => void handleToggleFlowChart()}
        aria-expanded={flowChartOpen}
      >
        <span className={`${styles.flowChartArrow} ${flowChartOpen ? styles.open : ''}`}>▶</span>
        Event lifecycle diagram
      </button>

      {flowChartOpen && (
        <div className={styles.flowChartContainer} aria-label="Event lifecycle state machine diagram">
          {flowChartLoading && <p className={styles.flowChartLoading}>Loading diagram…</p>}
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


