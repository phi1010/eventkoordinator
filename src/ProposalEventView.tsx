import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import {
  fetchProposal,
  fetchProposalEvents,
  fetchSeriesById,
  type ProposalDetail,
  type ProposalEventSummary,
  type Series,
  type Event,
} from './api'
import { EventEditor } from './EventEditor'
import styles from './ProposalEventView.module.css'

export function ProposalEventView() {
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
        setError(err instanceof Error ? err.message : 'Failed to load proposal data')
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
        setError(err instanceof Error ? err.message : 'Failed to load event')
      } finally {
        setEventLoading(false)
      }
    }

    loadEvent()
  }, [eventId, proposalEvents])

  const handleEventUpdate = useCallback((updated: Event) => {
    setEvent(updated)
    if (proposalId) {
      fetchProposalEvents(proposalId).then(setProposalEvents).catch(console.error)
    }
  }, [proposalId])

  if (loading) {
    return <div className={styles.loading}>Loading proposal...</div>
  }

  if (error) {
    return <div className={styles.error}>{error}</div>
  }

  if (!proposal || !proposalId) {
    return <div className={styles.error}>Proposal not found</div>
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
          ← Back to Proposal
        </Link>

        <h2>{proposal.title}</h2>

        <div className={styles.infoRow}>
          <span className={styles.infoLabel}>Duration Days</span>
          <span className={styles.infoValue}>{proposal.duration_days}</span>
        </div>
        <div className={styles.infoRow}>
          <span className={styles.infoLabel}>Time per Day</span>
          <span className={styles.infoValue}>{proposal.duration_time_per_day}</span>
        </div>
        <div className={styles.infoRow}>
          <span className={styles.infoLabel}>Occurrences</span>
          <span className={styles.infoValue}>{proposal.occurrence_count}</span>
        </div>
        <div className={styles.infoRow}>
          <span className={styles.infoLabel}>Submission Type</span>
          <span className={styles.infoValue}>{proposal.submission_type}</span>
        </div>

        <h3>Preferred Dates</h3>
        <p style={{ fontSize: '0.85rem', color: '#555', whiteSpace: 'pre-wrap' }}>
          {proposal.preferred_dates || 'Not specified'}
        </p>

        <h3>Linked Events ({proposalEvents.length})</h3>
        {proposalEvents.length === 0 ? (
          <p style={{ fontSize: '0.85rem', color: '#888' }}>No events linked yet</p>
        ) : (
          <ul className={styles.timeslotsList}>
            {proposalEvents.map((ev) => (
              <li
                key={ev.id}
                className={ev.id === eventId ? styles.linkedEventItem : undefined}
                style={{ cursor: 'pointer' }}
                onClick={() => navigate(`/proposal/${proposalId}/event/${ev.id}`)}
              >
                <strong>{ev.name}</strong>
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
        {eventLoading ? (
          <div className={styles.loading}>Loading event...</div>
        ) : event && series ? (
          <div>
            {/* Series display */}
            <div className={styles.seriesSelector}>
              <span className={styles.seriesLabel}>Series</span>
              <div className={styles.seriesValue}>{series.name}</div>
            </div>

            <EventEditor
              key={event.id}
              series={series}
              event={event}
              onEventUpdate={handleEventUpdate}
            />
          </div>
        ) : (
          <div className={styles.error}>Event not found. It may not be linked to this proposal.</div>
        )}
      </div>
    </div>
  )
}

