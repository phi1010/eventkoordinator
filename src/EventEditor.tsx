import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Event, Series, ExternalCalendarEvent } from './api'
import {
  fetchSyncStatus,
  fetchExternalCalendarEvents,
  pushToPlatform,
  updateEvent,
  type EventSyncInfo,
} from './api'
import type { CalendarEvent, Resource } from './calendarTypes'
import WeekViewCombined from './WeekViewCombined'
import { useUnsavedChanges } from './useUnsavedChanges'
import styles from './SubEventEditor.module.css'

interface EventEditorProps {
  series: Series
  event: Event
  onEventUpdate: (updated: Event) => void
  onRequestNavigation?: (confirmFn: () => Promise<boolean>) => void
  disabled?: boolean
}

function parseLocalDateTimeInput(value: string): Date | null {
  if (!value) return null
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

function toLocalDateTimeInputValue(date: Date | string): string {
  const d = typeof date === 'string' ? new Date(date) : date
  if (!d || Number.isNaN(d.getTime())) return ''
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${y}-${m}-${day}T${hh}:${mm}`
}

export function EventEditor({ series, event, onEventUpdate, onRequestNavigation, disabled = false }: EventEditorProps) {
  const navigate = useNavigate()
  const [syncInfo, setSyncInfo] = useState<EventSyncInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [pushing, setPushing] = useState<string | null>(null)

  // Edit form state
  const [name, setName] = useState(event.name)
  const [startTime, setStartTime] = useState(toLocalDateTimeInputValue(event.startTime))
  const [endTime, setEndTime] = useState(toLocalDateTimeInputValue(event.endTime))
  const [tag, setTag] = useState(event.tag || '')
  const [useFullDays, setUseFullDays] = useState(event.useFullDays || false)
  const [changedFields, setChangedFields] = useState<Set<string>>(new Set())
  const [isSaving, setIsSaving] = useState(false)
  const [editError, setEditError] = useState<string | null>(null)

  // Calendar reference state – calendarRange is driven solely by WeekViewCombined's onWeekRangeChange
  const [calendarRange, setCalendarRange] = useState<{ startUtc: string; endUtc: string } | null>(null)
  const [externalEvents, setExternalEvents] = useState<ExternalCalendarEvent[]>([])
  const [calendarLoading, setCalendarLoading] = useState(false)
  const [calendarError, setCalendarError] = useState<string | null>(null)

  // Track unsaved changes
  const hasChanges = changedFields.size > 0
  const { confirmNavigation } = useUnsavedChanges(hasChanges)

  const calendarResources = useMemo<Resource[]>(() => [
    {
      id: 'event-editor-resource',
      name: 'Event Schedule',
      color: '#2e7d32',
    },
  ], [])

  const calendarEvents = useMemo<CalendarEvent[]>(() => {
    const referenceEvents: CalendarEvent[] = externalEvents.map((reference) => ({
      id: reference.id,
      resourceId: 'event-editor-resource',
      title: `${reference.title} (${reference.source})`,
      startUtc: reference.startUtc,
      endUtc: reference.endUtc,
      color: '#90a4ae',
    }))

    const selectedStart = parseLocalDateTimeInput(startTime)
    const selectedEnd = parseLocalDateTimeInput(endTime)
    let editedEvents: CalendarEvent[] = []

    if (selectedStart && selectedEnd && selectedEnd > selectedStart) {
      if (useFullDays) {
        // Single continuous event spanning over midnight
        editedEvents = [
          {
            id: `edited-${event.id}`,
            resourceId: 'event-editor-resource',
            title: name || event.name,
            startUtc: selectedStart.toISOString(),
            endUtc: selectedEnd.toISOString(),
            color: '#2e7d32',
          },
        ]
      } else {
        // Split into per-day blocks using the same daily start/end hours
        const startHours = selectedStart.getHours()
        const startMinutes = selectedStart.getMinutes()
        const endHours = selectedEnd.getHours()
        const endMinutes = selectedEnd.getMinutes()

        // Calculate the number of calendar days this event spans
        const startDay = new Date(selectedStart.getFullYear(), selectedStart.getMonth(), selectedStart.getDate())
        const endDay = new Date(selectedEnd.getFullYear(), selectedEnd.getMonth(), selectedEnd.getDate())
        const dayCount = Math.round((endDay.getTime() - startDay.getTime()) / 86_400_000) + 1

        if (dayCount <= 1) {
          // Single day event, no splitting needed
          editedEvents = [
            {
              id: `edited-${event.id}`,
              resourceId: 'event-editor-resource',
              title: name || event.name,
              startUtc: selectedStart.toISOString(),
              endUtc: selectedEnd.toISOString(),
              color: '#2e7d32',
            },
          ]
        } else {
          // Multi-day: each day gets start hours → end hours
          for (let i = 0; i < dayCount; i++) {
            const day = new Date(startDay.getFullYear(), startDay.getMonth(), startDay.getDate() + i)
            const dayStart = new Date(day)
            dayStart.setHours(startHours, startMinutes, 0, 0)
            const dayEnd = new Date(day)
            dayEnd.setHours(endHours, endMinutes, 0, 0)

            // Correct days where end <= start (edge-case times, e.g. overnight block)
            if (dayEnd <= dayStart) {
              dayEnd.setDate(dayEnd.getDate() + 1)
              if (dayEnd > selectedEnd) continue
            }

            editedEvents.push({
              id: `edited-${event.id}-day${i}`,
              resourceId: 'event-editor-resource',
              title: name || event.name,
              startUtc: dayStart.toISOString(),
              endUtc: dayEnd.toISOString(),
              color: '#2e7d32',
            })
          }
        }
      }
    }

    return [...referenceEvents, ...editedEvents]
  }, [endTime, event.id, event.name, externalEvents, name, startTime, useFullDays])

  // Expose confirmation function to parent
  useEffect(() => {
    if (onRequestNavigation) {
      onRequestNavigation(confirmNavigation)
    }
  }, [onRequestNavigation, confirmNavigation])

  // Reset form state when event changes
  useEffect(() => {
    setName(event.name)
    setStartTime(toLocalDateTimeInputValue(event.startTime))
    setEndTime(toLocalDateTimeInputValue(event.endTime))
    setTag(event.tag || '')
    setUseFullDays(event.useFullDays || false)
    setChangedFields(new Set())
    setEditError(null)
    // calendarRange is not set here – the remounted WeekViewCombined will
    // call onWeekRangeChange once, which is the single source of truth.
  }, [event.id, event.name, event.startTime, event.endTime, event.tag, event.useFullDays])

  useEffect(() => {
    const loadSyncStatus = async () => {
      try {
        setLoading(true)
        const data = await fetchSyncStatus(series.id, event.id)
        setSyncInfo(data)
        setError(null)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to fetch sync status')
      } finally {
        setLoading(false)
      }
    }

    loadSyncStatus()
  }, [series.id, event.id])

  useEffect(() => {
    if (!calendarRange) return

    const loadExternalEvents = async () => {
      try {
        setCalendarLoading(true)
        const data = await fetchExternalCalendarEvents(calendarRange.startUtc, calendarRange.endUtc)
        setExternalEvents(data)
        setCalendarError(null)
      } catch (err) {
        setCalendarError(err instanceof Error ? err.message : 'Failed to fetch calendar references')
      } finally {
        setCalendarLoading(false)
      }
    }

    loadExternalEvents()
  }, [calendarRange])

  const handleNameChange = (value: string) => {
    setName(value)
    setChangedFields((prev) => new Set(prev).add('name'))
    setEditError(null)
  }

  const handleStartTimeChange = (value: string) => {
    setStartTime(value)
    setChangedFields((prev) => new Set(prev).add('startTime'))
    setEditError(null)
  }

  const handleEndTimeChange = (value: string) => {
    setEndTime(value)
    setChangedFields((prev) => new Set(prev).add('endTime'))
    setEditError(null)
  }

  const handleTagChange = (value: string) => {
    setTag(value)
    setChangedFields((prev) => new Set(prev).add('tag'))
    setEditError(null)
  }

  const handleUseFullDaysChange = (value: boolean) => {
    setUseFullDays(value)
    setChangedFields((prev) => new Set(prev).add('useFullDays'))
    setEditError(null)
  }

  const handleCalendarSelection = (selection: Omit<CalendarEvent, 'id'>) => {
    handleStartTimeChange(toLocalDateTimeInputValue(new Date(selection.startUtc)))
    handleEndTimeChange(toLocalDateTimeInputValue(new Date(selection.endUtc)))
  }

  const handleSaveChanges = async () => {
    try {
      setIsSaving(true)
      setEditError(null)

      const updates: Record<string, unknown> = {}
      if (changedFields.has('name') && name !== event.name) {
        updates.name = name
      }
      if (changedFields.has('startTime') && startTime !== toLocalDateTimeInputValue(event.startTime)) {
        updates.startTime = parseLocalDateTimeInput(startTime)?.toISOString()
      }
      if (changedFields.has('endTime') && endTime !== toLocalDateTimeInputValue(event.endTime)) {
        updates.endTime = parseLocalDateTimeInput(endTime)?.toISOString()
      }
      if (changedFields.has('tag') && tag !== event.tag) {
        updates.tag = tag || null
      }
      if (changedFields.has('useFullDays') && useFullDays !== (event.useFullDays || false)) {
        updates.useFullDays = useFullDays
      }

      if (Object.keys(updates).length === 0) {
        setChangedFields(new Set())
        return
      }

      const updated = await updateEvent({
        seriesId: series.id,
        eventId: event.id,
        name: updates.name as string | undefined,
        startTime: updates.startTime as string | undefined,
        endTime: updates.endTime as string | undefined,
        tag: updates.tag as string | null | undefined,
        useFullDays: updates.useFullDays as boolean | undefined,
      })

      onEventUpdate(updated)

      setName(updated.name)
      setStartTime(toLocalDateTimeInputValue(updated.startTime))
      setEndTime(toLocalDateTimeInputValue(updated.endTime))
      setTag(updated.tag || '')
      setUseFullDays(updated.useFullDays || false)
      setChangedFields(new Set())
    } catch (err) {
      setEditError(err instanceof Error ? err.message : 'Failed to save event')
    } finally {
      setIsSaving(false)
    }
  }

  const handleCancel = () => {
    setName(event.name)
    setStartTime(toLocalDateTimeInputValue(event.startTime))
    setEndTime(toLocalDateTimeInputValue(event.endTime))
    setTag(event.tag || '')
    setUseFullDays(event.useFullDays || false)
    setChangedFields(new Set())
    setEditError(null)
  }

  const handlePush = async (platform: string) => {
    try {
      setPushing(platform)
      await pushToPlatform(series.id, event.id, platform)

      // Refresh sync status
      const data = await fetchSyncStatus(series.id, event.id)
      setSyncInfo(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to push data')
    } finally {
      setPushing(null)
    }
  }

  const handleViewDiff = (platform: string) => {
    navigate(`/sync/diff/${series.id}/${event.id}/${encodeURIComponent(platform)}`)
  }

  const getStatusColor = (status: string): string => {
    switch (status) {
      case 'entry up-to-date':
        return '#4caf50' // green
      case 'entry differs':
        return '#ff9800' // orange
      case 'no entry exists':
        return '#2196f3' // blue
      default:
        return '#666'
    }
  }

  const getStatusLabel = (status: string): string => {
    switch (status) {
      case 'entry up-to-date':
        return '✓ Up to date'
      case 'entry differs':
        return '⚠ Differs'
      case 'no entry exists':
        return '⊘ No entry'
      default:
        return status
    }
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2>Edit Event</h2>
        <p className={styles.eventName}>{event.name}</p>
      </div>

      {/* Edit Form */}
      <div className={styles.editSection}>
        <h3>Event Details</h3>
        <form className={styles.editForm} aria-label="Edit event details">
          <div className={styles.formGroup}>
            <label htmlFor="event-name" className={styles.label}>
              Name
              {changedFields.has('name') && <span className={styles.changedIndicator} aria-label="unsaved change">●</span>}
            </label>
            <input
              id="event-name"
              type="text"
              value={name}
              onChange={(e) => handleNameChange(e.target.value)}
              className={`${styles.formInput} ${changedFields.has('name') ? styles.changed : ''}`}
              disabled={isSaving || disabled}
            />
          </div>

          <div className={styles.formRow}>
            <div className={styles.formGroup}>
              <label htmlFor="event-start-time" className={styles.label}>
                Start Time
                {changedFields.has('startTime') && <span className={styles.changedIndicator} aria-label="unsaved change">●</span>}
              </label>
              <input
                id="event-start-time"
                type="datetime-local"
                value={startTime}
                onChange={(e) => handleStartTimeChange(e.target.value)}
                className={`${styles.formInput} ${changedFields.has('startTime') ? styles.changed : ''}`}
                disabled={isSaving || disabled}
              />
            </div>

            <div className={styles.formGroup}>
              <label htmlFor="event-end-time" className={styles.label}>
                End Time
                {changedFields.has('endTime') && <span className={styles.changedIndicator} aria-label="unsaved change">●</span>}
              </label>
              <input
                id="event-end-time"
                type="datetime-local"
                value={endTime}
                onChange={(e) => handleEndTimeChange(e.target.value)}
                className={`${styles.formInput} ${changedFields.has('endTime') ? styles.changed : ''}`}
                disabled={isSaving || disabled}
              />
            </div>
          </div>

          <div className={styles.formGroup}>
            <label htmlFor="event-tag" className={styles.label}>
              Tag
              {changedFields.has('tag') && <span className={styles.changedIndicator} aria-label="unsaved change">●</span>}
            </label>
            <input
              id="event-tag"
              type="text"
              value={tag}
              onChange={(e) => handleTagChange(e.target.value)}
              placeholder="e.g., workshop, keynote, break"
              className={`${styles.formInput} ${changedFields.has('tag') ? styles.changed : ''}`}
              disabled={isSaving || disabled}
            />
          </div>

          <div className={styles.formGroup}>
            <label className={styles.checkboxLabel}>
              <input
                id="event-use-full-days"
                type="checkbox"
                checked={useFullDays}
                onChange={(e) => handleUseFullDaysChange(e.target.checked)}
                disabled={isSaving || disabled}
                aria-describedby="event-use-full-days-desc"
              />
              <span>
                Span full days
                {changedFields.has('useFullDays') && <span className={styles.changedIndicator} aria-label="unsaved change">●</span>}
              </span>
            </label>
            <p id="event-use-full-days-desc" className={styles.fieldDescription}>
              When checked, the event spans continuously over midnight (e.g. Mon 08:00 → Tue 16:00
              shows as one block). When unchecked, multi-day events are split into daily blocks
              using the same daily start/end hours (e.g. Mon 08:00–16:00 and Tue 08:00–16:00).
            </p>
          </div>

          {editError && <div className={styles.editError} role="alert">{editError}</div>}

          <div className={styles.buttonGroup}>
            <button
              type="button"
              onClick={handleSaveChanges}
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

      {/* Calendar Time Picker */}
      <div className={styles.calendarSection}>
        <h3>Pick Time in Calendar</h3>
        <p className={styles.calendarHint}>
          Displayed in local time. Stored in UTC. {disabled ? 'View only - no edit permission.' : 'Drag on the calendar to update start and end.'}
        </p>
        {calendarLoading && <p className={styles.loading}>Loading reference calendar events...</p>}
        {calendarError && <p className={styles.error}>{calendarError}</p>}
        <div className={styles.calendarWrapper} style={disabled ? { opacity: 0.6, pointerEvents: 'none' } : undefined}>
          <WeekViewCombined
            key={event.id}
            resources={calendarResources}
            events={calendarEvents}
            startDate={event.startTime}
            onEventCreate={handleCalendarSelection}
            onWeekRangeChange={setCalendarRange}
            disabled={disabled}
          />
        </div>
      </div>

      {/* Sync Section */}
      <div className={styles.syncSection}>
        <h3>Synchronization Status</h3>

        {loading && <p className={styles.loading}>Loading sync status...</p>}
        {error && <p className={styles.error}>{error}</p>}

        {syncInfo && (
          <div className={styles.syncGrid}>
            {syncInfo.sync_statuses.map((sync) => (
              <div key={sync.platform} className={styles.syncCard}>
                <div className={styles.cardHeader}>
                  <h4>{sync.platform}</h4>
                  <div
                    className={styles.statusBadge}
                    style={{ backgroundColor: getStatusColor(sync.status) }}
                  >
                    {getStatusLabel(sync.status)}
                  </div>
                </div>

                <div className={styles.cardBody}>
                  {sync.last_synced && (
                    <div className={styles.info}>
                      <span className={styles.infoLabel}>Last synced:</span>
                      <span className={styles.infoValue}>
                        {new Date(sync.last_synced).toLocaleDateString('de-DE', {
                          month: 'short',
                          day: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </span>
                    </div>
                  )}

                  {sync.last_error && (
                    <div className={styles.error}>
                      <span className={styles.infoLabel}>Error:</span>
                      <span className={styles.infoValue}>{sync.last_error}</span>
                    </div>
                  )}
                </div>

                <button
                  type="button"
                  className={styles.pushButton}
                  onClick={() => handlePush(sync.platform)}
                  disabled={pushing === sync.platform}
                  aria-label={`Push or update event to ${sync.platform}`}
                >
                  {pushing === sync.platform ? 'Pushing...' : 'Push/Update'}
                </button>

                <button
                  type="button"
                  className={styles.diffButton}
                  onClick={() => handleViewDiff(sync.platform)}
                  disabled={pushing === sync.platform}
                  aria-label={`View differences for ${sync.platform}`}
                >
                  View Diff
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className={styles.footer}>
        <p className={styles.note}>
          Changes to this event will be synchronized across all platforms.
        </p>
      </div>
    </div>
  )
}

