import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { DataTable, type DataTableExpandedRows, type DataTableRowEvent } from 'primereact/datatable'
import { Column } from 'primereact/column'
import { MultiSelect, type MultiSelectChangeEvent } from 'primereact/multiselect'
import {
  fetchProposalsList,
  fetchProposalEvents,
  fetchSyncStatus,
  type ProposalListItem,
  type ProposalEventSummary,
  type EventSyncInfo,
} from './api'
import { usePermissions } from './usePermissions'
import styles from './ProposalDashboard.module.css'

// ── helpers ──────────────────────────────────────────────────────────────────

function formatDatetimeSpan(startTime: string, endTime: string): string {
  const start = new Date(startTime)
  const end = new Date(endTime)
  const datePart = start.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })
  const startT = start.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })
  const endDate = end.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })
  if (datePart !== endDate) {
    const endT = end.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })
    return `${datePart} ${startT} – ${endDate} ${endT}`
  }
  const endT = end.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })
  return `${datePart}  ${startT} – ${endT}`
}

function ProposalStatusBadge({ status }: { status: string }) {
  const { t } = useTranslation()
  const cls = `${styles.badge} ${styles[`badge--${status}`] ?? styles['badge--unknown']}`
  const label = t(`proposal.statusValues.${status}`, status)
  return <span className={cls}>{label}</span>
}

function EventStatusBadge({ status }: { status: string }) {
  const { t } = useTranslation()
  const cls = `${styles.badge} ${styles[`badge--event-${status}`] ?? styles['badge--unknown']}`
  const label = t(`event.statusValues.${status}`, status)
  return <span className={cls}>{label}</span>
}

function SyncStatusBadge({ platform, status }: { platform: string; status: string }) {
  const clsMap: Record<string, string> = {
    'entry up-to-date': styles['syncBadge--up-to-date'],
    'entry differs': styles['syncBadge--differs'],
    'creation pending': styles['syncBadge--creation-pending'],
    'no entry exists': styles['syncBadge--no-entry'],
    'status unknown': styles['syncBadge--unknown'],
  }
  const cls = `${styles.syncBadge} ${clsMap[status] ?? styles['syncBadge--unknown']}`
  return <span className={cls}>{platform}</span>
}

// ── helpers ──────────────────────────────────────────────────────────────────

function AgreedDatesBar({ accepted, intended }: { accepted: number; intended: number }) {
  const pct = intended > 0 ? Math.min((accepted / intended) * 100, 100) : 0
  return (
    <div className={styles.progressCell}>
      <div className={styles.progressBar}>
        <div className={styles.progressFill} style={{ width: `${pct}%` }} />
      </div>
      <span className={styles.progressLabel}>{accepted}/{intended}</span>
    </div>
  )
}

// ── column definitions ────────────────────────────────────────────────────────

type ColKey =
  | 'creator' | 'speakers' | 'type' | 'status' | 'agreedDates'
  | 'eventDatetime' | 'eventStatus' | 'eventSync'

const ALL_COLUMN_KEYS: ColKey[] = [
  'creator', 'speakers', 'type', 'status', 'agreedDates',
  'eventDatetime', 'eventStatus', 'eventSync',
]

const DEFAULT_VISIBLE: Record<ColKey, boolean> = {
  creator: true, speakers: true, type: true, status: true, agreedDates: true,
  eventDatetime: true, eventStatus: true, eventSync: true,
}

// ── expanded row data ─────────────────────────────────────────────────────────

interface ExpandedData {
  events: ProposalEventSummary[]
  syncStatus: Record<string, EventSyncInfo>
  loading: boolean
}

// ── main component ────────────────────────────────────────────────────────────

export function ProposalDashboard() {
  const { t } = useTranslation()
  const { canBrowse, loading: permissionsLoading } = usePermissions()

  const [proposals, setProposals] = useState<ProposalListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [expandedRows, setExpandedRows] = useState<DataTableExpandedRows>({})
  const [expandedData, setExpandedData] = useState<Record<string, ExpandedData>>({})

  const [visibleColumns, setVisibleColumns] = useState<Record<ColKey, boolean>>(DEFAULT_VISIBLE)

  useEffect(() => {
    fetchProposalsList()
      .then(setProposals)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false))
  }, [])

  const onRowExpand = useCallback(async (e: DataTableRowEvent) => {
    const proposal = e.data as ProposalListItem
    if (expandedData[proposal.id]) return

    setExpandedData(prev => ({ ...prev, [proposal.id]: { events: [], syncStatus: {}, loading: true } }))

    try {
      const events = await fetchProposalEvents(proposal.id)
      const syncStatus: Record<string, EventSyncInfo> = {}
      await Promise.all(
        events.map(async ev => {
          try {
            syncStatus[ev.id] = await fetchSyncStatus(ev.series_id, ev.id)
          } catch {
            // sync status optional — ignore errors
          }
        })
      )
      setExpandedData(prev => ({ ...prev, [proposal.id]: { events, syncStatus, loading: false } }))
    } catch {
      setExpandedData(prev => ({ ...prev, [proposal.id]: { events: [], syncStatus: {}, loading: false } }))
    }
  }, [expandedData])

  const rowExpansionTemplate = useCallback((data: ProposalListItem) => {
    const loaded = expandedData[data.id]
    if (!loaded || loaded.loading) {
      return <div className={styles.expandedSection}>{t('proposalDashboard.loadingEvents')}</div>
    }
    if (loaded.events.length === 0) {
      return <div className={styles.expandedSection}><span className={styles.noEvents}>{t('proposalDashboard.noEvents')}</span></div>
    }
    return (
      <div className={styles.expandedSection}>
        <DataTable value={loaded.events} size="small" showGridlines={false}>
          {visibleColumns.eventDatetime && (
            <Column
              header={t('proposalDashboard.columns.eventDatetime')}
              body={(ev: ProposalEventSummary) => formatDatetimeSpan(ev.startTime, ev.endTime)}
            />
          )}
          {visibleColumns.eventStatus && (
            <Column
              header={t('proposalDashboard.columns.eventStatus')}
              body={(ev: ProposalEventSummary) => <EventStatusBadge status={ev.status} />}
            />
          )}
          {visibleColumns.eventSync && (
            <Column
              header={t('proposalDashboard.columns.eventSync')}
              body={(ev: ProposalEventSummary) => {
                const info = loaded.syncStatus[ev.id]
                if (!info || info.sync_statuses.length === 0) return null
                return (
                  <div className={styles.syncBadges}>
                    {info.sync_statuses.map(s => (
                      <SyncStatusBadge key={s.target_id} platform={s.platform} status={s.status} />
                    ))}
                  </div>
                )
              }}
            />
          )}
        </DataTable>
      </div>
    )
  }, [expandedData, visibleColumns, t])

  // ── column toggle MultiSelect ───────────────────────────────────────────────

  const columnToggleOptions = [
    {
      label: t('proposalDashboard.proposalColumns'),
      items: [
        { key: 'creator',        label: t('proposalDashboard.columns.creator') },
        { key: 'speakers',       label: t('proposalDashboard.columns.speakers') },
        { key: 'type',           label: t('proposalDashboard.columns.type') },
        { key: 'status',         label: t('proposalDashboard.columns.status') },
        { key: 'agreedDates',    label: t('proposalDashboard.columns.agreedDates') },
      ],
    },
    {
      label: t('proposalDashboard.eventColumns'),
      items: [
        { key: 'eventDatetime', label: t('proposalDashboard.columns.eventDatetime') },
        { key: 'eventStatus',   label: t('proposalDashboard.columns.eventStatus') },
        { key: 'eventSync',     label: t('proposalDashboard.columns.eventSync') },
      ],
    },
  ]

  const selectedColumnKeys = ALL_COLUMN_KEYS.filter(k => visibleColumns[k])

  const onColumnToggle = (e: MultiSelectChangeEvent) => {
    const selected = e.value as ColKey[]
    const next = { ...visibleColumns }
    ALL_COLUMN_KEYS.forEach(k => { next[k] = selected.includes(k) })
    setVisibleColumns(next)
  }

  const tableHeader = (
    <div className={styles.tableHeader}>
      <span className={styles.tableTitle}>{t('proposalDashboard.title')}</span>
      <MultiSelect
        value={selectedColumnKeys}
        options={columnToggleOptions}
        optionGroupLabel="label"
        optionGroupChildren="items"
        optionLabel="label"
        optionValue="key"
        onChange={onColumnToggle}
        placeholder={t('proposalDashboard.toggleColumns')}
        display="chip"
        style={{ maxWidth: '32rem' }}
      />
    </div>
  )

  // ── guards ────────────────────────────────────────────────────────────────

  if (permissionsLoading) return null

  if (!canBrowse('proposal')) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center', color: '#666' }}>
        <p style={{ fontSize: '1.2rem', marginBottom: '1rem' }}>{t('common.accessDenied')}</p>
        <p>{t('common.noPermissionBrowseProposal')}</p>
      </div>
    )
  }

  if (error) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center', color: '#b91c1c' }}>
        <p>{t('common.error')}: {error}</p>
      </div>
    )
  }

  // ── render ────────────────────────────────────────────────────────────────

  return (
    <div className={styles.container}>
      <DataTable
        value={proposals}
        loading={loading}
        expandedRows={expandedRows}
        onRowToggle={e => setExpandedRows(e.data as DataTableExpandedRows)}
        onRowExpand={onRowExpand}
        rowExpansionTemplate={rowExpansionTemplate}
        header={tableHeader}
        sortMode="multiple"
        removableSort
        size="small"
        showGridlines
        dataKey="id"
      >
        <Column expander style={{ width: '3rem' }} />
        <Column
          field="title"
          header={t('proposalDashboard.columns.title')}
          sortable
        />
        {visibleColumns.creator && (
          <Column
            header={t('proposalDashboard.columns.creator')}
            body={(p: ProposalListItem) => p.owner?.username ?? '—'}
            sortable
            sortField="owner.username"
          />
        )}
        {visibleColumns.speakers && (
          <Column
            header={t('proposalDashboard.columns.speakers')}
            body={(p: ProposalListItem) => (
              <div className={styles.speakerList}>
                {p.speakers.length > 0
                  ? p.speakers.map((s, i) => <div key={i}>{s}</div>)
                  : '—'}
              </div>
            )}
          />
        )}
        {visibleColumns.type && (
          <Column
            field="submission_type"
            header={t('proposalDashboard.columns.type')}
            sortable
            body={(p: ProposalListItem) => p.submission_type ?? '—'}
          />
        )}
        {visibleColumns.status && (
          <Column
            field="status"
            header={t('proposalDashboard.columns.status')}
            sortable
            body={(p: ProposalListItem) => <ProposalStatusBadge status={p.status} />}
          />
        )}
        {visibleColumns.agreedDates && (
          <Column
            header={t('proposalDashboard.columns.agreedDates')}
            sortable
            sortField="accepted_event_count"
            style={{ minWidth: '10rem' }}
            body={(p: ProposalListItem) => (
              <AgreedDatesBar accepted={p.accepted_event_count} intended={p.occurrence_count} />
            )}
          />
        )}
      </DataTable>
    </div>
  )
}
