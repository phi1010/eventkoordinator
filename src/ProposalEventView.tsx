import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  fetchProposal,
  fetchProposalEvents,
  fetchSeriesById,
  checkObjectPermission,
  type ProposalDetail,
  type ProposalEventSummary,
  type Series,
  type Event,
} from './api'
import { EventEditor } from './EventEditor'
import { EventStatusBadge } from './EventStatusBadge'
import styles from './ProposalEventView.module.css'

export function ProposalEventView() {
  const { t } = useTranslation()
  const { proposalId, eventId } = useParams<{ proposalId: string; eventId: string }>()
  const navigate = useNavigate()

  const [proposal, setProposal] = useState<ProposalDetail | null>(null)
  const [proposalEvents, setProposalEvents] = useState<ProposalEventSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // For the event editor
  const [series, setSeries] = useState<Series | null>(null)
  const [event, setEvent] = useState<Event | null>(null)
  const [eventLoading, setEventLoading] = useState(false)
  const [eventPermissionLoading, setEventPermissionLoading] = useState(false)
  const [canEditEvent, setCanEditEvent] = useState(false)
  const [canDeleteEvent, setCanDeleteEvent] = useState(false)

  // Load proposal details and linked events
  useEffect(() => {
    if (!proposalId) return

    const loadData = async () => {
      try {
        setLoading(true)
        setError(null)
        const [proposalData, eventsData] = await Promise.all([
          fetchProposal(proposalId),
          fetchProposalEvents(proposalId),
        ])
        setProposal(proposalData)
        setProposalEvents(eventsData)
      } catch (err) {
        setError(err instanceof Error ? err.message : t('api.proposals.notFound'))
      } finally {
        setLoading(false)
      }
    }

    loadData()
  }, [proposalId])

  // Load event and series when editing an existing event
  useEffect(() => {
    if (!eventId) return

    const loadEvent = async () => {
      // Find which series contains this event from the proposalEvents list
      const linkedEvent = proposalEvents.find((e) => e.id === eventId)
      if (!linkedEvent) {
        return
      }

      try {
        setEventLoading(true)
        const seriesData = await fetchSeriesById(linkedEvent.series_id)
        setSeries(seriesData)
        const eventData = seriesData.events.find((e) => e.id === eventId)
        if (eventData) {
          setEvent(eventData)
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : t('api.events.notFound'))
      } finally {
        setEventLoading(false)
      }
    }

    loadEvent()
  }, [eventId, proposalEvents])

  useEffect(() => {
    if (!event) {
      setCanEditEvent(false)
      setCanDeleteEvent(false)
      return
    }

    const loadPermissions = async () => {
      try {
        setEventPermissionLoading(true)
        const [canChange, canDelete] = await Promise.all([
          checkObjectPermission({
            app: 'apiv1',
            action: 'change',
            object_type: 'event',
            object_id: event.id,
          }),
          checkObjectPermission({
            app: 'apiv1',
            action: 'delete',
            object_type: 'event',
            object_id: event.id,
          }),
        ])
        setCanEditEvent(canChange)
        setCanDeleteEvent(canDelete)
      } finally {
        setEventPermissionLoading(false)
      }
    }

    void loadPermissions()
  }, [event])

  const handleEventUpdate = useCallback((updated: Event) => {
    setEvent(updated)
    if (proposalId) {
      fetchProposalEvents(proposalId).then(setProposalEvents).catch(console.error)
    }
  }, [proposalId])

  if (loading) {
    return <div className={styles.loading}>{t('proposal.loading')}</div>
  }

  if (error) {
    return <div className={styles.error}>{error}</div>
  }

  if (!proposal || !proposalId) {
    return <div className={styles.error}>{t('api.proposals.notFound')}</div>
  }

  const formatDateTime = (isoStr: string) => {
    const d = new Date(isoStr)
    return d.toLocaleDateString('de-DE', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  return (
    <div className={styles.container}>
      {/* Left panel: Proposal info */}
      <div className={styles.proposalInfoPanel}>
        <Link to={`/proposal-editor/${proposalId}`} className={styles.backLink}>
          ← {t('common.back')}
        </Link>

        <h2>{proposal.title}</h2>

        <div className={styles.infoRow}>
          <span className={styles.infoLabel}>{t('proposal.numberOfDays')}</span>
          <span className={styles.infoValue}>{proposal.duration_days}</span>
        </div>
        <div className={styles.infoRow}>
          <span className={styles.infoLabel}>{t('proposal.timePerDay')}</span>
          <span className={styles.infoValue}>{proposal.duration_time_per_day}</span>
        </div>
        <div className={styles.infoRow}>
          <span className={styles.infoLabel}>{t('proposal.occurrenceCount')}</span>
          <span className={styles.infoValue}>{proposal.occurrence_count}</span>
        </div>
        <div className={styles.infoRow}>
          <span className={styles.infoLabel}>{t('proposal.submissionType')}</span>
          <span className={styles.infoValue}>{proposal.submission_type}</span>
        </div>

        <h3>{t('proposal.preferredDates')}</h3>
        <p style={{ fontSize: '0.85rem', color: '#555', whiteSpace: 'pre-wrap' }}>
          {proposal.preferred_dates || t('api.notSpecified')}
        </p>

        <h3>{t('proposal.linkedEvents', {count:proposalEvents.length})}</h3>
        {proposalEvents.length === 0 ? (
          <p style={{ fontSize: '0.85rem', color: '#888' }}>{t('proposal.noEventsYet')}</p>
        ) : (
          <ul className={styles.timeslotsList}>
            {proposalEvents.map((ev) => (
              <li
                key={ev.id}
                className={ev.id === eventId ? styles.linkedEventItem : undefined}
                style={{ cursor: 'pointer' }}
                onClick={() => navigate(`/proposal/${proposalId}/event/${ev.id}`)}
              >
                <div className={styles.linkedEventHeader}>
                  <strong className={styles.linkedEventName}>{ev.name}</strong>
                  <EventStatusBadge
                    status={ev.status}
                    ariaLabel={`Status of ${ev.name}: ${ev.status}`}
                  />
                </div>
                <br />
                <small>{ev.series_name}</small>
                <br />
                <small>{formatDateTime(ev.startTime)} – {formatDateTime(ev.endTime)}</small>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Right panel: Event editor */}
      <div className={styles.eventEditorPanel}>
        {eventLoading || eventPermissionLoading ? (
          <div className={styles.loading}>{t('event.loading')}</div>
        ) : event && series ? (
          <div>
            {/* Series display */}
            <div className={styles.seriesSelector}>
              <span className={styles.seriesLabel}>{t('series')}</span>
              <div className={styles.seriesValue}>{series.name}</div>
            </div>

            <EventEditor
              key={event.id}
              series={series}
              event={event}
              onEventUpdate={handleEventUpdate}
              disabled={!canEditEvent}
              canDelete={canDeleteEvent}
            />
          </div>
        ) : (
          <div className={styles.error}>{t('api.events.notFound')}. {t('proposal.mayNotLinked')}</div>
        )}
      </div>
    </div>
  )
}

