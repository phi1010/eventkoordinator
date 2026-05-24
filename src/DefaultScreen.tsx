import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { usePermissions } from './usePermissions'
import {
  fetchCalls,
  createProposal,
  searchProposals,
  type CallOut,
  type ProposalSummary,
} from './api'
import styles from './DefaultScreen.module.css'

function formatDate(isoDate: string): string {
  try {
    return new Date(isoDate).toLocaleDateString('de-DE', {
      day: '2-digit', month: '2-digit', year: 'numeric',
    })
  } catch {
    return isoDate
  }
}

function formatDateRange(start: string, end: string): string {
  try {
    const s = new Date(start)
    const e = new Date(end)
    const opts: Intl.DateTimeFormatOptions = { month: 'long', year: 'numeric' }
    const sf = s.toLocaleDateString('de-DE', opts)
    const ef = e.toLocaleDateString('de-DE', opts)
    return sf === ef ? sf : `${sf} – ${ef}`
  } catch {
    return `${start} – ${end}`
  }
}

function daysUntilDate(isoDate: string): number {
  const [year, month, day] = isoDate.split('-').map(Number)
  const deadline = new Date(year, month - 1, day)
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return Math.round((deadline.getTime() - today.getTime()) / (1000 * 60 * 60 * 24))
}

interface CallCardProps {
  call: CallOut
  myProposals: ProposalSummary[]
  onSubmit: (callId: string) => void
  onOpenProposal: (proposalId: string) => void
  onLoginToSubmit: () => void
  isSubmitting: boolean
  canAddProposal: boolean
  t: ReturnType<typeof useTranslation>['t']
}

function CallCard({ call, myProposals, onSubmit, onOpenProposal, onLoginToSubmit, isSubmitting, canAddProposal, t }: CallCardProps) {
  const d1 = daysUntilDate(call.submission_deadline)
  const d2 = daysUntilDate(call.print_deadline)
  const upcomingDays = [d1, d2].filter(d => d >= 0)
  const isOverdue = upcomingDays.length === 0
  const days = isOverdue ? -1 : Math.min(...upcomingDays)
  const isUrgent = !isOverdue && days <= 7

  const dateClass = (d: number) => {
    if (d < 0) return styles.callMetaValueExpired
    if (!isOverdue && d === days) return styles.callMetaValueNearest
    return styles.callMetaValue
  }

  const badgeClass = isOverdue
    ? styles.deadlineBadgeOverdue
    : isUrgent
      ? styles.deadlineBadgeUrgent
      : styles.deadlineBadgeOk

  const badgeText = isOverdue
    ? t('call.overdue')
    : days === 0
      ? t('call.today')
      : t('call.daysLeft', { count: days })

  return (
    <div className={styles.callCard}>
      <div className={styles.callCardBody}>
        <div className={styles.callCardTitleRow}>
          <h2 className={styles.callCardTitle}>{call.title}</h2>
          <span className={`${styles.deadlineBadge} ${badgeClass}`}>{badgeText}</span>
        </div>

        {call.description && (
          <p className={styles.callCardDescription}>{call.description}</p>
        )}

        <div className={styles.callMeta}>
          <div className={styles.callMetaRow}>
            <span>
              {t('call.executionPeriod')}:{' '}
              <strong className={styles.callMetaValue}>
                {formatDateRange(call.execution_period_start, call.execution_period_end)}
              </strong>
            </span>
            <span>
              {t('call.deadline')}:{' '}
              <strong className={dateClass(d1)}>{formatDate(call.submission_deadline)}</strong>
            </span>
          </div>
          <div className={styles.callMetaRow}>
            <span>
              {t('call.printDeadline')}:{' '}
              <strong className={dateClass(d2)}>{formatDate(call.print_deadline)}</strong>
            </span>
          </div>
          <div className={styles.callMetaRow}>
            <span>
              {t('call.responsible')}:{' '}
              <a
                href={`mailto:${call.responsible_email}`}
                className={styles.responsibleLink}
              >
                {call.responsible_name}
              </a>
            </span>
          </div>
        </div>
      </div>

      {myProposals.length > 0 && (
        <div className={styles.submissionsSection}>
          <p className={styles.submissionsSectionLabel}>
            {t('call.myProposalsForCall')}
          </p>
          {myProposals.map((p) => (
            <div key={p.id} className={styles.submissionRow}>
              <div className={styles.submissionInfo}>
                <span>{p.title || t('proposal.untitledProposal')}</span>
              </div>
              <button
                type="button"
                className={styles.submissionOpenBtn}
                onClick={() => onOpenProposal(String(p.id))}
              >
                {t('call.open')}
              </button>
            </div>
          ))}
        </div>
      )}

      <div className={styles.callCardFooter}>
        {canAddProposal ? (
          <button
            type="button"
            className={styles.btnSubmit}
            onClick={() => onSubmit(String(call.id))}
            disabled={isSubmitting || isOverdue}
          >
            {myProposals.length > 0 ? t('call.submitAnother') : t('call.submitNew')}
          </button>
        ) : (
          <button
            type="button"
            className={styles.btnLoginToSubmit}
            onClick={onLoginToSubmit}
          >
            {t('call.loginToSubmit')}
          </button>
        )}
      </div>
    </div>
  )
}

export function DefaultScreen() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { canBrowse, canAdd, loading: permissionsLoading } = usePermissions()

  const [calls, setCalls] = useState<CallOut[]>([])
  const [myProposals, setMyProposals] = useState<ProposalSummary[]>([])
  const [loadingCalls, setLoadingCalls] = useState(true)
  const [callsError, setCallsError] = useState(false)
  const [submittingCallId, setSubmittingCallId] = useState<string | null>(null)

  const canViewProposals = !permissionsLoading && canBrowse('proposal')
  const canViewSeries = !permissionsLoading && canBrowse('series')
  const canAddProposal = !permissionsLoading && canAdd('proposal')

  // Load calls for all users — the endpoint is publicly accessible
  useEffect(() => {
    const load = async () => {
      setLoadingCalls(true)
      setCallsError(false)
      try {
        const callsData = await fetchCalls(true)
        setCalls(callsData)
      } catch {
        setCallsError(true)
      } finally {
        setLoadingCalls(false)
      }
    }
    void load()
  }, [])

  // Load own proposals separately — requires browse_proposal permission
  useEffect(() => {
    if (permissionsLoading || !canViewProposals) return
    const loadProposals = async () => {
      try {
        const proposalsData = await searchProposals('')
        setMyProposals(proposalsData)
      } catch {
        // Non-critical — proposals list just stays empty
      }
    }
    void loadProposals()
  }, [permissionsLoading, canViewProposals])

  const handleSubmitForCall = async (callId: string) => {
    setSubmittingCallId(callId)
    try {
      const newProposal = await createProposal({ call_id: callId })
      navigate(`/proposal-editor/${newProposal.id}`)
    } catch {
      // fall through — user stays on page
    } finally {
      setSubmittingCallId(null)
    }
  }

  const handleLoginToSubmit = () => {
    window.location.href = `/oidc/authenticate/?next=${encodeURIComponent(window.location.pathname + window.location.search)}`
  }

  const proposalsForCall = (callId: string) =>
    myProposals.filter((p) => p.call_id === callId)

  const unassignedProposals = myProposals.filter((p) => !p.call_id)

  return (
    <div className={styles.container}>
      <div className={styles.content}>
        <div className={styles.pageHeader}>
          <h1 className={styles.title}>{t('call.sectionTitle')}</h1>
          <p className={styles.subtitle}>{t('call.sectionSubtitle')}</p>
        </div>

        {loadingCalls && (
          <p className={styles.stateBox}>{t('call.loadingCalls')}</p>
        )}

        {callsError && (
          <p className={styles.stateBox}>{t('defaultScreen.errorLoadingCalls')}</p>
        )}

        {!loadingCalls && !callsError && calls.length === 0 && (
          <p className={styles.stateBox}>{t('call.noActiveCalls')}</p>
        )}

        {!loadingCalls && !callsError && calls.length > 0 && (
          <div className={styles.callList}>
            {calls.map((call) => (
              <CallCard
                key={String(call.id)}
                call={call}
                myProposals={proposalsForCall(String(call.id))}
                onSubmit={handleSubmitForCall}
                onOpenProposal={(id) => navigate(`/proposal-editor/${id}`)}
                onLoginToSubmit={handleLoginToSubmit}
                isSubmitting={submittingCallId === String(call.id)}
                canAddProposal={canAddProposal}
                t={t}
              />
            ))}
          </div>
        )}

        {canViewProposals && unassignedProposals.length > 0 && (
          <div className={styles.otherSection}>
            <h2 className={styles.otherSectionTitle}>{t('call.otherProposals')}</h2>
            <div className={styles.otherList}>
              {unassignedProposals.map((p) => (
                <div key={String(p.id)} className={styles.otherProposalRow}>
                  <div className={styles.otherProposalInfo}>
                    <span>{p.title || t('proposal.untitledProposal')}</span>
                  </div>
                  <button
                    type="button"
                    className={styles.submissionOpenBtn}
                    onClick={() => navigate(`/proposal-editor/${p.id}`)}
                  >
                    {t('call.open')}
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {!permissionsLoading && canViewSeries && (
          <div className={styles.coordinatorLink}>
            <button
              type="button"
              className={styles.coordinatorLinkBtn}
              onClick={() => navigate('/coordinator')}
            >
              {t('defaultScreen.coordinatorLink')}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
