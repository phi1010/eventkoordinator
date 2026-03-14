import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Event, Series, ExternalCalendarEvent } from './api'
import {
  fetchSyncStatus,
  fetchExternalCalendarEvents,
  pushToPlatform,
  updateEvent,
  fetchCalculatedPrices,
  createCalculatedPrices,
  updateCalculatedPrices,
  deleteCalculatedPrices,
  getUserPermissions,
  checkObjectPermission,
  type CalculatedPrices,
  type EventSyncInfo,
} from './api'
import type { CalendarEvent, Resource } from './calendarTypes'
import WeekViewCombined from './WeekViewCombined'
import { useUnsavedChanges } from './useUnsavedChanges'
import { EventTransitionButtons } from './EventTransitionButtons'
import styles from './SubEventEditor.module.css'

interface EventEditorProps {
  series: Series
  event: Event
  onEventUpdate: (updated: Event) => void
  onDeleteEvent?: () => Promise<void>
  onRequestNavigation?: (confirmFn: () => Promise<boolean>) => void
  disabled?: boolean
  canDelete?: boolean
}

interface CalculatedPricesFormValues {
  member_regular_gross_eur: string
  member_discounted_gross_eur: string
  guest_regular_gross_eur: string
  guest_discounted_gross_eur: string
  business_net_eur: string
}

const EMPTY_CALCULATED_PRICES_FORM: CalculatedPricesFormValues = {
  member_regular_gross_eur: '',
  member_discounted_gross_eur: '',
  guest_regular_gross_eur: '',
  guest_discounted_gross_eur: '',
  business_net_eur: '',
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

function toCalculatedPricesForm(values: CalculatedPrices): CalculatedPricesFormValues {
  return {
    member_regular_gross_eur: values.member_regular_gross_eur ?? '',
    member_discounted_gross_eur: values.member_discounted_gross_eur ?? '',
    guest_regular_gross_eur: values.guest_regular_gross_eur ?? '',
    guest_discounted_gross_eur: values.guest_discounted_gross_eur ?? '',
    business_net_eur: values.business_net_eur ?? '',
  }
}

function toNullableDecimal(value: string): string | null {
  const trimmed = value.trim()
  return trimmed.length > 0 ? trimmed : null
}

export function EventEditor({ series, event, onEventUpdate, onDeleteEvent, onRequestNavigation, disabled = false, canDelete = false }: EventEditorProps) {
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
  const [isDeleting, setIsDeleting] = useState(false)
  const [editError, setEditError] = useState<string | null>(null)
  const [calculatedPrices, setCalculatedPrices] = useState<CalculatedPrices | null>(null)
  const [calculatedPricesForm, setCalculatedPricesForm] = useState<CalculatedPricesFormValues>(
    EMPTY_CALCULATED_PRICES_FORM
  )
  const [calculatedPricesDirty, setCalculatedPricesDirty] = useState(false)
  const [calculatedPricesLoading, setCalculatedPricesLoading] = useState(true)
  const [calculatedPricesSaving, setCalculatedPricesSaving] = useState(false)
  const [calculatedPricesDeleting, setCalculatedPricesDeleting] = useState(false)
  const [calculatedPricesCreateMode, setCalculatedPricesCreateMode] = useState<'default' | 'blank' | null>(null)
  const [calculatedPricesError, setCalculatedPricesError] = useState<string | null>(null)
  const [canViewCalculatedPrices, setCanViewCalculatedPrices] = useState(false)
  const [canAddCalculatedPrices, setCanAddCalculatedPrices] = useState(false)
  const [canChangeCalculatedPrices, setCanChangeCalculatedPrices] = useState(false)
  const [canDeleteCalculatedPrices, setCanDeleteCalculatedPrices] = useState(false)

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

  useEffect(() => {
    let isMounted = true

    const loadCalculatedPrices = async () => {
      try {
        setCalculatedPricesLoading(true)
        setCalculatedPricesError(null)
        setCalculatedPricesDirty(false)

        const permissions = await getUserPermissions()
        const canAdd = permissions.is_superuser || permissions.permissions.includes('add_calculatedprices')
        if (!isMounted) {
          return
        }
        setCanAddCalculatedPrices(canAdd)

        const prices = await fetchCalculatedPrices(series.id, event.id)
        if (!isMounted) {
          return
        }

        if (!prices) {
          setCalculatedPrices(null)
          setCalculatedPricesForm(EMPTY_CALCULATED_PRICES_FORM)
          setCanViewCalculatedPrices(false)
          setCanChangeCalculatedPrices(false)
          setCanDeleteCalculatedPrices(false)
          return
        }

        setCalculatedPrices(prices)
        setCalculatedPricesForm(toCalculatedPricesForm(prices))

        const [canView, canChange, canDelete] = await Promise.all([
          checkObjectPermission({
            app: 'sync_pretix',
            action: 'view',
            object_type: 'calculatedprices',
            object_id: prices.id,
          }),
          checkObjectPermission({
            app: 'sync_pretix',
            action: 'change',
            object_type: 'calculatedprices',
            object_id: prices.id,
          }),
          checkObjectPermission({
            app: 'sync_pretix',
            action: 'delete',
            object_type: 'calculatedprices',
            object_id: prices.id,
          }),
        ])

        if (!isMounted) {
          return
        }

        setCanViewCalculatedPrices(canView)
        setCanChangeCalculatedPrices(canChange)
        setCanDeleteCalculatedPrices(canDelete)
      } catch (err) {
        if (!isMounted) {
          return
        }
        setCalculatedPricesError(err instanceof Error ? err.message : 'Failed to load calculated prices')
        setCalculatedPrices(null)
        setCalculatedPricesForm(EMPTY_CALCULATED_PRICES_FORM)
        setCanViewCalculatedPrices(false)
        setCanChangeCalculatedPrices(false)
        setCanDeleteCalculatedPrices(false)
      } finally {
        if (isMounted) {
          setCalculatedPricesLoading(false)
        }
      }
    }

    void loadCalculatedPrices()

    return () => {
      isMounted = false
    }
  }, [series.id, event.id])

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

  const handleDelete = async () => {
    const confirmed = window.confirm(
      `Delete the event "${event.name}"? This cannot be undone.`
    )
    if (!confirmed) {
      return
    }

    try {
      setIsDeleting(true)
      setEditError(null)
      await onDeleteEvent?.()
    } catch (err) {
      setEditError(err instanceof Error ? err.message : 'Failed to delete event')
    } finally {
      setIsDeleting(false)
    }
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

  const handleCalculatedPriceFieldChange = (field: keyof CalculatedPricesFormValues, value: string) => {
    setCalculatedPricesForm((prev) => ({ ...prev, [field]: value }))
    setCalculatedPricesDirty(true)
    setCalculatedPricesError(null)
  }

  const handleCreateCalculatedPrices = async (useDefaultPricingConfiguration: boolean) => {
    try {
      setCalculatedPricesError(null)
      setCalculatedPricesCreateMode(useDefaultPricingConfiguration ? 'default' : 'blank')

      const created = await createCalculatedPrices(series.id, event.id, useDefaultPricingConfiguration)
      setCalculatedPrices(created)
      setCalculatedPricesForm(toCalculatedPricesForm(created))
      setCalculatedPricesDirty(false)

      const [canView, canChange, canDelete] = await Promise.all([
        checkObjectPermission({
          app: 'sync_pretix',
          action: 'view',
          object_type: 'calculatedprices',
          object_id: created.id,
        }),
        checkObjectPermission({
          app: 'sync_pretix',
          action: 'change',
          object_type: 'calculatedprices',
          object_id: created.id,
        }),
        checkObjectPermission({
          app: 'sync_pretix',
          action: 'delete',
          object_type: 'calculatedprices',
          object_id: created.id,
        }),
      ])

      setCanViewCalculatedPrices(canView)
      setCanChangeCalculatedPrices(canChange)
      setCanDeleteCalculatedPrices(canDelete)
    } catch (err) {
      setCalculatedPricesError(err instanceof Error ? err.message : 'Failed to create calculated prices')
    } finally {
      setCalculatedPricesCreateMode(null)
    }
  }

  const handleSaveCalculatedPrices = async () => {
    if (!calculatedPrices) {
      return
    }

    try {
      setCalculatedPricesSaving(true)
      setCalculatedPricesError(null)

      const updated = await updateCalculatedPrices({
        seriesId: series.id,
        eventId: event.id,
        member_regular_gross_eur: toNullableDecimal(calculatedPricesForm.member_regular_gross_eur),
        member_discounted_gross_eur: toNullableDecimal(calculatedPricesForm.member_discounted_gross_eur),
        guest_regular_gross_eur: toNullableDecimal(calculatedPricesForm.guest_regular_gross_eur),
        guest_discounted_gross_eur: toNullableDecimal(calculatedPricesForm.guest_discounted_gross_eur),
        business_net_eur: toNullableDecimal(calculatedPricesForm.business_net_eur),
      })

      setCalculatedPrices(updated)
      setCalculatedPricesForm(toCalculatedPricesForm(updated))
      setCalculatedPricesDirty(false)
    } catch (err) {
      setCalculatedPricesError(err instanceof Error ? err.message : 'Failed to save calculated prices')
    } finally {
      setCalculatedPricesSaving(false)
    }
  }

  const handleDeleteCalculatedPrices = async () => {
    if (!calculatedPrices) {
      return
    }

    const confirmed = window.confirm('Delete calculated prices for this event? This cannot be undone.')
    if (!confirmed) {
      return
    }

    try {
      setCalculatedPricesDeleting(true)
      setCalculatedPricesError(null)
      await deleteCalculatedPrices(series.id, event.id)
      setCalculatedPrices(null)
      setCalculatedPricesForm(EMPTY_CALCULATED_PRICES_FORM)
      setCalculatedPricesDirty(false)
      setCanViewCalculatedPrices(false)
      setCanChangeCalculatedPrices(false)
      setCanDeleteCalculatedPrices(false)
    } catch (err) {
      setCalculatedPricesError(err instanceof Error ? err.message : 'Failed to delete calculated prices')
    } finally {
      setCalculatedPricesDeleting(false)
    }
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
              disabled={disabled || !hasChanges || isSaving || isDeleting}
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
            {canDelete && onDeleteEvent && (
              <button
                type="button"
                onClick={() => void handleDelete()}
                disabled={isSaving || isDeleting}
                className={styles.deleteButton}
              >
                {isDeleting ? 'Deleting...' : 'Delete Event'}
              </button>
            )}
          </div>
        </form>

        {/* Workflow status & transition buttons */}
        <EventTransitionButtons
          seriesId={series.id}
          eventId={event.id}
          currentStatus={(event.status as string | undefined) ?? 'draft'}
          onTransitionSuccess={(updatedEvent) => onEventUpdate(updatedEvent)}
        />
      </div>

      <div className={styles.calculatedPricesSection}>
        <h3>Calculated Prices</h3>

        {calculatedPricesLoading && <p className={styles.loading}>Loading calculated prices...</p>}
        {!calculatedPricesLoading && calculatedPricesError && <p className={styles.error}>{calculatedPricesError}</p>}

        {!calculatedPricesLoading && !calculatedPrices && !calculatedPricesError && (
          <div className={styles.calculatedPricesEmptyState}>
            <p className={styles.note}>No calculated prices exist for this event yet.</p>
            {canAddCalculatedPrices ? (
              <div className={styles.buttonGroup}>
                <button
                  type="button"
                  className={styles.saveButton}
                  onClick={() => void handleCreateCalculatedPrices(true)}
                  disabled={calculatedPricesCreateMode !== null}
                >
                  {calculatedPricesCreateMode === 'default' ? 'Generating...' : 'Generate with Default Config'}
                </button>
                <button
                  type="button"
                  className={styles.cancelButton}
                  onClick={() => void handleCreateCalculatedPrices(false)}
                  disabled={calculatedPricesCreateMode !== null}
                >
                  {calculatedPricesCreateMode === 'blank' ? 'Creating...' : 'Create Blank Values'}
                </button>
              </div>
            ) : (
              <p className={styles.note}>You do not have permission to create calculated prices.</p>
            )}
          </div>
        )}

        {!calculatedPricesLoading && calculatedPrices && !canViewCalculatedPrices && (
          <p className={styles.note}>You do not have permission to view calculated prices for this event.</p>
        )}

        {!calculatedPricesLoading && calculatedPrices && canViewCalculatedPrices && (
          <div className={styles.calculatedPricesForm}>
            <div className={styles.formGroup}>
              <label htmlFor="pricing-config-id" className={styles.label}>Pricing Configuration</label>
              <input
                id="pricing-config-id"
                type="text"
                value={calculatedPrices.pricing_configuration_id ?? 'None (manual)'}
                className={styles.formInput}
                disabled
              />
            </div>

            <div className={styles.calculatedPricesGrid}>
              <div className={styles.formGroup}>
                <label htmlFor="member-regular-gross" className={styles.label}>Member Regular Gross (EUR)</label>
                <input
                  id="member-regular-gross"
                  type="text"
                  value={calculatedPricesForm.member_regular_gross_eur}
                  onChange={(e) => handleCalculatedPriceFieldChange('member_regular_gross_eur', e.target.value)}
                  className={styles.formInput}
                  disabled={!canChangeCalculatedPrices || calculatedPricesSaving}
                />
              </div>

              <div className={styles.formGroup}>
                <label htmlFor="member-discounted-gross" className={styles.label}>Member Discounted Gross (EUR)</label>
                <input
                  id="member-discounted-gross"
                  type="text"
                  value={calculatedPricesForm.member_discounted_gross_eur}
                  onChange={(e) => handleCalculatedPriceFieldChange('member_discounted_gross_eur', e.target.value)}
                  className={styles.formInput}
                  disabled={!canChangeCalculatedPrices || calculatedPricesSaving}
                />
              </div>

              <div className={styles.formGroup}>
                <label htmlFor="guest-regular-gross" className={styles.label}>Guest Regular Gross (EUR)</label>
                <input
                  id="guest-regular-gross"
                  type="text"
                  value={calculatedPricesForm.guest_regular_gross_eur}
                  onChange={(e) => handleCalculatedPriceFieldChange('guest_regular_gross_eur', e.target.value)}
                  className={styles.formInput}
                  disabled={!canChangeCalculatedPrices || calculatedPricesSaving}
                />
              </div>

              <div className={styles.formGroup}>
                <label htmlFor="guest-discounted-gross" className={styles.label}>Guest Discounted Gross (EUR)</label>
                <input
                  id="guest-discounted-gross"
                  type="text"
                  value={calculatedPricesForm.guest_discounted_gross_eur}
                  onChange={(e) => handleCalculatedPriceFieldChange('guest_discounted_gross_eur', e.target.value)}
                  className={styles.formInput}
                  disabled={!canChangeCalculatedPrices || calculatedPricesSaving}
                />
              </div>

              <div className={styles.formGroup}>
                <label htmlFor="business-net" className={styles.label}>Business Net (EUR)</label>
                <input
                  id="business-net"
                  type="text"
                  value={calculatedPricesForm.business_net_eur}
                  onChange={(e) => handleCalculatedPriceFieldChange('business_net_eur', e.target.value)}
                  className={styles.formInput}
                  disabled={!canChangeCalculatedPrices || calculatedPricesSaving}
                />
              </div>
            </div>

            <div className={styles.buttonGroup}>
              {canChangeCalculatedPrices ? (
                <button
                  type="button"
                  className={styles.saveButton}
                  onClick={() => void handleSaveCalculatedPrices()}
                  disabled={!calculatedPricesDirty || calculatedPricesSaving || calculatedPricesDeleting}
                >
                  {calculatedPricesSaving ? 'Saving...' : 'Save Calculated Prices'}
                </button>
              ) : (
                <p className={styles.note}>You do not have permission to change calculated prices.</p>
              )}

              {canDeleteCalculatedPrices && (
                <button
                  type="button"
                  className={styles.deleteButton}
                  onClick={() => void handleDeleteCalculatedPrices()}
                  disabled={calculatedPricesDeleting || calculatedPricesSaving}
                >
                  {calculatedPricesDeleting ? 'Deleting...' : 'Delete Calculated Prices'}
                </button>
              )}
            </div>
          </div>
        )}
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

