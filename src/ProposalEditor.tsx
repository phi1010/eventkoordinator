import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  fetchProposal,
  updateProposal,
  fetchProposalChecklist,
  fetchProposalHistory,
  fetchProposalSpeakers,
  fetchSubmissionTypes,
  fetchProposalLanguages,
  fetchProposalAreas,
  searchUsers,
  fetchProposalEvents,
  fetchProposalTransitions,
  createEvent,
  searchSeriesAutocomplete,
  type ProposalChecklistItem,
  type ProposalHistoryEntry,
  type ProposalSpeakerOut,
  type LookupItem,
  type UserBasic,
  type ProposalEventSummary,
  type Series,
} from './api'
import { useUnsavedChanges } from './useUnsavedChanges'
import { SpeakerListEditor } from './SpeakerListEditor'
import { ProposalTransitionButtons } from './ProposalTransitionButtons'
import styles from './EventGeneralEditor.module.css'

interface ProposalFormData {
  // General section
  title: string
  submission_type: string
  area: string
  language: string
  abstract: string
  description: string
  internal_notes: string
  occurrence_count: number
  duration_days: number
  duration_time_per_day: string

  // Additional information section
  is_basic_course: boolean
  max_participants: number
  material_cost_eur: string
  preferred_dates: string

  // Profile section
  is_regular_member: boolean
  has_building_access: boolean
}

interface ProposalEditorProps {
  proposalId?: string
  canEdit?: boolean
  onProposalSave?: (formData: ProposalFormData) => void
  onRequestNavigation?: (confirmFn: () => Promise<boolean>) => void
}

const DEFAULT_FORM_DATA: ProposalFormData = {
  title: '',
  submission_type: '',
  area: '',
  language: '',
  abstract: '',
  description: '',
  internal_notes: '',
  occurrence_count: 0,
  duration_days: 1,
  duration_time_per_day: '00:00',

  is_basic_course: false,
  max_participants: 0,
  material_cost_eur: '0.00',
  preferred_dates: '',

  is_regular_member: false,
  has_building_access: false,
}

function pad2(value: number): string {
  return value.toString().padStart(2, '0')
}

function formatLocalIso(dateValue: string): string {
  const date = new Date(dateValue)
  if (Number.isNaN(date.getTime())) {
    return dateValue
  }

  const year = date.getFullYear()
  const month = pad2(date.getMonth() + 1)
  const day = pad2(date.getDate())
  const hours = pad2(date.getHours())
  const minutes = pad2(date.getMinutes())
  const seconds = pad2(date.getSeconds())

  const offsetMinutes = -date.getTimezoneOffset()
  const sign = offsetMinutes >= 0 ? '+' : '-'
  const absOffset = Math.abs(offsetMinutes)
  const offsetHours = pad2(Math.floor(absOffset / 60))
  const offsetMins = pad2(absOffset % 60)

  return `${year}-${month}-${day} ${hours}:${minutes}:${seconds} ${sign}${offsetHours}:${offsetMins}`
}

function formatRelativeTime(dateValue: string): string {
  const date = new Date(dateValue)
  if (Number.isNaN(date.getTime())) {
    return 'just now'
  }

  const deltaMs = Date.now() - date.getTime()
  const deltaSeconds = Math.max(0, Math.floor(deltaMs / 1000))

  if (deltaSeconds < 60) {
    return 'just now'
  }

  const minutes = Math.floor(deltaSeconds / 60)
  if (minutes < 60) {
    return `${minutes} minute${minutes === 1 ? '' : 's'} ago`
  }

  const hours = Math.floor(minutes / 60)
  if (hours < 24) {
    return `${hours} hour${hours === 1 ? '' : 's'} ago`
  }

  const days = Math.floor(hours / 24)
  if (days < 30) {
    return `${days} day${days === 1 ? '' : 's'} ago`
  }

  const months = Math.floor(days / 30)
  if (months < 12) {
    return `${months} month${months === 1 ? '' : 's'} ago`
  }

  const years = Math.floor(months / 12)
  return `${years} year${years === 1 ? '' : 's'} ago`
}

export function ProposalEditor({ proposalId: _proposalId, canEdit = false, onProposalSave, onRequestNavigation }: ProposalEditorProps) {
  const navigate = useNavigate()
  const [formData, setFormData] = useState<ProposalFormData>(DEFAULT_FORM_DATA)
  const [changedFields, setChangedFields] = useState<Set<string>>(new Set())
  const [isSaving, setIsSaving] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [checklist, setChecklist] = useState<Record<string, ProposalChecklistItem>>({})
  const [checklistLoading, setChecklistLoading] = useState(false)
  const [history, setHistory] = useState<ProposalHistoryEntry[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [speakers, setSpeakers] = useState<ProposalSpeakerOut[]>([])
  const [submissionTypes, setSubmissionTypes] = useState<LookupItem[]>([])
  const [proposalLanguages, setProposalLanguages] = useState<LookupItem[]>([])
  const [proposalAreas, setProposalAreas] = useState<LookupItem[]>([])
  const [lookupLoading, setLookupLoading] = useState(true)
  const [owner, setOwner] = useState<UserBasic | null>(null)
  const [editors, setEditors] = useState<UserBasic[]>([])
  const [participantSearchQuery, setParticipantSearchQuery] = useState('')
  const [participantSearchResults, setParticipantSearchResults] = useState<UserBasic[]>([])
  const [linkedEvents, setLinkedEvents] = useState<ProposalEventSummary[]>([])
  const [linkedEventsLoading, setLinkedEventsLoading] = useState(false)
  const [currentStatus, setCurrentStatus] = useState<string>('')

  // Event creation state
  const [seriesSearchQuery, setSeriesSearchQuery] = useState('')
  const [seriesSearchResults, setSeriesSearchResults] = useState<Series[]>([])
  const [selectedSeriesId, setSelectedSeriesId] = useState<string>('')
  const [isCreatingEvent, setIsCreatingEvent] = useState(false)
  const [createEventError, setCreateEventError] = useState<string | null>(null)
  const latestHistoryEntry = history.reduce<ProposalHistoryEntry | null>((latest, entry) => {
    if (!latest) return entry
    return new Date(entry.timestamp).getTime() > new Date(latest.timestamp).getTime() ? entry : latest
  }, null)
  const historyBadge = latestHistoryEntry
    ? `last changed ${formatRelativeTime(latestHistoryEntry.timestamp)}`
    : 'no recent changes'

  // Load proposal data when proposalId changes
  useEffect(() => {
    if (_proposalId && _proposalId.trim()) {
      const loadProposal = async () => {
        try {
          setIsLoading(true)
          setError(null)
          const data = await fetchProposal(_proposalId)
          setFormData({
            title: data.title,
            submission_type: data.submission_type,
            area: data.area || '',
            language: data.language || '',
            abstract: data.abstract,
            description: data.description,
            internal_notes: data.internal_notes,
            occurrence_count: data.occurrence_count,
            duration_days: data.duration_days,
            duration_time_per_day: data.duration_time_per_day,
            is_basic_course: data.is_basic_course,
            max_participants: data.max_participants,
            material_cost_eur: data.material_cost_eur,
            preferred_dates: data.preferred_dates,
            is_regular_member: data.is_regular_member,
            has_building_access: data.has_building_access,
          })
          setOwner(data.owner || null)
          setEditors(data.editors || [])
          setChangedFields(new Set())
        } catch (err) {
          setError(err instanceof Error ? err.message : 'Failed to load proposal')
          console.error('Failed to load proposal:', err)
        } finally {
          setIsLoading(false)
        }
      }
      loadProposal()
    }
  }, [_proposalId])

  // Load proposal checklist when proposalId changes
  useEffect(() => {
    if (_proposalId && _proposalId.trim()) {
      const loadChecklist = async () => {
        try {
          setChecklistLoading(true)
          const data = await fetchProposalChecklist(_proposalId)
          setChecklist(data)
        } catch (err) {
          console.error('Failed to load checklist:', err)
        } finally {
          setChecklistLoading(false)
        }
      }
      loadChecklist()
    }
  }, [_proposalId])

  // Load proposal history when proposalId changes
  useEffect(() => {
    if (_proposalId && _proposalId.trim()) {
      const loadHistory = async () => {
        try {
          setHistoryLoading(true)
          const data = await fetchProposalHistory(_proposalId, 7)
          setHistory(data.entries)
        } catch (err) {
          console.error('Failed to load history:', err)
        } finally {
          setHistoryLoading(false)
        }
      }
      loadHistory()
    }
  }, [_proposalId])

  // Load speakers when proposalId changes
  useEffect(() => {
    if (_proposalId && _proposalId.trim()) {
      const loadSpeakers = async () => {
        try {
          const data = await fetchProposalSpeakers(_proposalId)
          setSpeakers(data)
        } catch (err) {
          console.error('Failed to load speakers:', err)
        }
      }
      loadSpeakers()
    }
  }, [_proposalId])

  // Load linked events and current status when proposalId changes
  useEffect(() => {
    if (_proposalId && _proposalId.trim()) {
      const loadLinkedEvents = async () => {
        try {
          setLinkedEventsLoading(true)
          const events = await fetchProposalEvents(_proposalId)
          setLinkedEvents(events)
        } catch (err) {
          console.error('Failed to load linked events:', err)
        } finally {
          setLinkedEventsLoading(false)
        }
      }
      const loadStatus = async () => {
        try {
          const data = await fetchProposalTransitions(_proposalId)
          setCurrentStatus(data.current_status)
        } catch (err) {
          console.error('Failed to load proposal status:', err)
        }
      }
      loadLinkedEvents()
      loadStatus()
    }
  }, [_proposalId])

  // Debounced series search for event creation
  useEffect(() => {
    const timer = setTimeout(async () => {
      try {
        const results = await searchSeriesAutocomplete(seriesSearchQuery)
        setSeriesSearchResults(results)
      } catch (err) {
        console.error('Failed to search series:', err)
      }
    }, 300)
    return () => clearTimeout(timer)
  }, [seriesSearchQuery])

  const handleCreateEvent = async () => {
    if (!selectedSeriesId || !_proposalId) return
    try {
      setIsCreatingEvent(true)
      setCreateEventError(null)
      const newEvent = await createEvent({
        seriesId: selectedSeriesId,
        name: formData.title + ' Session',
        proposal_id: _proposalId,
      })
      navigate(`/proposal/${_proposalId}/event/${newEvent.id}`)
    } catch (err) {
      setCreateEventError(err instanceof Error ? err.message : 'Failed to create event')
    } finally {
      setIsCreatingEvent(false)
    }
  }

  // Load submission types, languages, and areas on mount
  useEffect(() => {
    const loadLookups = async () => {
      try {
        setLookupLoading(true)
        const [types, languages, areas] = await Promise.all([
          fetchSubmissionTypes(),
          fetchProposalLanguages(),
          fetchProposalAreas(),
        ])
        setSubmissionTypes(types)
        setProposalLanguages(languages)
        setProposalAreas(areas)
      } catch (err) {
        console.error('Failed to load lookup tables:', err)
      } finally {
        setLookupLoading(false)
      }
    }
    loadLookups()
  }, [])

  // Track unsaved changes
  const hasChanges = changedFields.size > 0
  const { confirmNavigation } = useUnsavedChanges(hasChanges)

  // Expose confirmation function to parent
  useEffect(() => {
    if (onRequestNavigation) {
      onRequestNavigation(confirmNavigation)
    }
  }, [onRequestNavigation, confirmNavigation])


  // Debounced participant search
  useEffect(() => {
    if (!participantSearchQuery.trim()) {
      setParticipantSearchResults([])
      return
    }

    const timer = setTimeout(async () => {
      try {
        const results = await searchUsers(participantSearchQuery)
        setParticipantSearchResults(results)
      } catch (err) {
        console.error('Failed to search users:', err)
      }
    }, 300)

    return () => clearTimeout(timer)
  }, [participantSearchQuery])

  const handleFieldChange = (fieldName: keyof ProposalFormData, value: unknown) => {
    setFormData((prev) => ({
      ...prev,
      [fieldName]: value,
    }))
    setChangedFields((prev) => new Set(prev).add(fieldName))
    setError(null)
  }


  const handleRemoveEditor = (userId: string) => {
    setEditors((prev) => prev.filter((p) => p.id !== userId))
    setChangedFields((prev) => new Set(prev).add('editors'))
    setError(null)
  }

  const handleSave = async () => {
    if (!_proposalId || !_proposalId.trim()) {
      setError('No proposal ID provided')
      return
    }

    try {
      setIsSaving(true)
      setError(null)


      // No validation - allow saving with incomplete data
      // Checklist will show what's missing

      // Build update payload with only changed fields
      // Convert empty strings to null for optional fields
      const updatePayload: Record<string, unknown> = {}
      const formFields: Array<keyof ProposalFormData> = [
        'title',
        'submission_type',
        'area',
        'language',
        'abstract',
        'description',
        'internal_notes',
        'occurrence_count',
        'duration_days',
        'duration_time_per_day',
        'is_basic_course',
        'max_participants',
        'material_cost_eur',
        'preferred_dates',
        'is_regular_member',
        'has_building_access',
      ]

      for (const fieldName of formFields) {
        if (!changedFields.has(fieldName)) {
          continue
        }
        const value = formData[fieldName]
        if (['submission_type', 'area', 'language'].includes(fieldName) && value === '') {
          updatePayload[fieldName] = null
        } else {
          updatePayload[fieldName] = value
        }
      }

      if (changedFields.has('editors')) {
        updatePayload.editor_ids = editors.map((p) => p.id)
      }

      // Save to API - only send changed fields
      await updateProposal(_proposalId, updatePayload)

      // Reload proposal data to get fresh state from server
      const freshData = await fetchProposal(_proposalId)
      setFormData({
        title: freshData.title,
        submission_type: freshData.submission_type,
        area: freshData.area || '',
        language: freshData.language || '',
        abstract: freshData.abstract,
        description: freshData.description,
        internal_notes: freshData.internal_notes,
        occurrence_count: freshData.occurrence_count,
        duration_days: freshData.duration_days,
        duration_time_per_day: freshData.duration_time_per_day,
        is_basic_course: freshData.is_basic_course,
        max_participants: freshData.max_participants,
        material_cost_eur: freshData.material_cost_eur,
        preferred_dates: freshData.preferred_dates,
        is_regular_member: freshData.is_regular_member,
        has_building_access: freshData.has_building_access,
      })
      setOwner(freshData.owner || null)
      setEditors(freshData.editors || [])

      // Reload checklist
      const freshChecklist = await fetchProposalChecklist(_proposalId)
      setChecklist(freshChecklist)

      // Reload speakers
      const freshSpeakers = await fetchProposalSpeakers(_proposalId)
      setSpeakers(freshSpeakers)

      setChangedFields(new Set())

      if (onProposalSave) {
        onProposalSave(formData)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save proposal')
    } finally {
      setIsSaving(false)
    }
  }

  const handleCancel = () => {
    setFormData(DEFAULT_FORM_DATA)
    setOwner(null)
    setEditors([])
    setParticipantSearchQuery('')
    setChangedFields(new Set())
    setError(null)
  }

  return (
    <div className={styles.container}>
      <h1>Proposal Editor</h1>

      {isLoading && <p aria-live="polite">Loading proposal...</p>}

      <form className={styles.form} aria-label="Proposal editor">
        {/* General Section */}
        <details
          className={styles.fieldset}
          name="proposal-editor-sections" open={true}
        >
          <summary className={styles.legend}>
            <span className={styles.summaryContent}>General Information</span>
          </summary>

          <div className={styles.detailsContent}>
              <div className={styles.formGroup}>
                <label htmlFor="proposal-title" className={styles.label}>
                  Title (max 30 characters)
                  {changedFields.has('title') && <span className={styles.changedIndicator} aria-label="unsaved change">●</span>}
                </label>
                <input
                  id="proposal-title"
                  type="text"
                  value={formData.title}
                  onChange={(e) => handleFieldChange('title', e.target.value.slice(0, 30))}
                  className={`${styles.input} ${changedFields.has('title') ? styles.changed : ''}`}
                  disabled={isSaving || !canEdit}
                  maxLength={30}
                  required
                />
                <small aria-live="polite">{formData.title.length}/30</small>
              </div>

              <div className={styles.formGroup}>
                <label htmlFor="proposal-submission-type" className={styles.label}>
                  Submission Type
                  {changedFields.has('submission_type') && <span className={styles.changedIndicator} aria-label="unsaved change">●</span>}
                </label>
                <select
                  id="proposal-submission-type"
                  value={formData.submission_type}
                  onChange={(e) => handleFieldChange('submission_type', e.target.value)}
                  className={`${styles.input} ${changedFields.has('submission_type') ? styles.changed : ''}`}
                  disabled={isSaving || lookupLoading || !canEdit}
                >
                  {lookupLoading ? (
                    <option value="">Loading...</option>
                  ) : submissionTypes.length === 0 ? (
                    <option value="">No submission types available</option>
                  ) : (
                    <>
                      <option value="">-- Select submission type --</option>
                      {submissionTypes.map((type) => (
                        <option key={type.code} value={type.code}>
                          {type.label}
                        </option>
                      ))}
                    </>
                  )}
                </select>
                <small className={styles.fieldHint}>
                  Workshop: Fixed booking, fee required, providers receive a remuneration; Open offer: No booking or fee required; takes place in the main building.
                </small>
              </div>

              <div className={styles.formGroup}>
                <label htmlFor="proposal-area" className={styles.label}>
                  Area (optional)
                  {changedFields.has('area') && <span className={styles.changedIndicator} aria-label="unsaved change">●</span>}
                </label>
                <select
                  id="proposal-area"
                  value={formData.area}
                  onChange={(e) => handleFieldChange('area', e.target.value)}
                  className={`${styles.input} ${changedFields.has('area') ? styles.changed : ''}`}
                  disabled={isSaving || !canEdit || lookupLoading}
                >
                  <option value="">-- Select an area --</option>
                  {proposalAreas.length === 0 ? (
                    <option disabled>Loading areas...</option>
                  ) : (
                    proposalAreas.map((area) => (
                      <option key={area.code} value={area.code}>
                        {area.label}
                      </option>
                    ))
                  )}
                </select>
              </div>

              <div className={styles.formGroup}>
                <label htmlFor="proposal-language" className={styles.label}>
                  Language
                  {changedFields.has('language') && <span className={styles.changedIndicator} aria-label="unsaved change">●</span>}
                </label>
                <select
                  id="proposal-language"
                  value={formData.language}
                  onChange={(e) => handleFieldChange('language', e.target.value)}
                  className={`${styles.input} ${changedFields.has('language') ? styles.changed : ''}`}
                  disabled={isSaving || lookupLoading || !canEdit}
                >
                  {lookupLoading ? (
                    <option value="">Loading...</option>
                  ) : proposalLanguages.length === 0 ? (
                    <option value="">No languages available</option>
                  ) : (
                    <>
                      <option value="">-- Select language --</option>
                      {proposalLanguages.map((lang) => (
                        <option key={lang.code} value={lang.code}>
                          {lang.label}
                        </option>
                      ))}
                    </>
                  )}
                </select>
              </div>

              <div className={styles.formGroup}>
                <label htmlFor="proposal-abstract" className={styles.label}>
                  Abstract (50-250 characters)
                  {changedFields.has('abstract') && <span className={styles.changedIndicator} aria-label="unsaved change">●</span>}
                </label>
                <textarea
                  id="proposal-abstract"
                  value={formData.abstract}
                  onChange={(e) => handleFieldChange('abstract', e.target.value)}
                  className={`${styles.textarea} ${changedFields.has('abstract') ? styles.changed : ''}`}
                  rows={3}
                  disabled={isSaving || !canEdit}
                  required
                />
                <small className={styles.fieldHint}>
                  This will be published on our website in the program overview. (50–250 characters)
                </small>
                <small aria-live="polite">{formData.abstract.length}/250</small>
              </div>

              <div className={styles.formGroup}>
                <label htmlFor="proposal-description" className={styles.label}>
                  Description (50-1000 characters)
                  {changedFields.has('description') && <span className={styles.changedIndicator} aria-label="unsaved change">●</span>}
                </label>
                <textarea
                  id="proposal-description"
                  value={formData.description}
                  onChange={(e) => handleFieldChange('description', e.target.value)}
                  className={`${styles.textarea} ${changedFields.has('description') ? styles.changed : ''}`}
                  rows={6}
                  disabled={isSaving || !canEdit}
                  required
                />
                <small className={styles.fieldHint}>
                  This will be published on our website in the detailed description. Please include goal, prerequisites and whether participants take something home. (50–1000 characters)
                </small>
                <small aria-live="polite">{formData.description.length}/1000</small>
              </div>

              <div className={styles.formGroup}>
                <label htmlFor="proposal-internal-notes" className={styles.label}>
                  Internal Notes (optional)
                  {changedFields.has('internal_notes') && <span className={styles.changedIndicator} aria-label="unsaved change">●</span>}
                </label>
                <textarea
                  id="proposal-internal-notes"
                  value={formData.internal_notes}
                  onChange={(e) => handleFieldChange('internal_notes', e.target.value)}
                  className={`${styles.textarea} ${changedFields.has('internal_notes') ? styles.changed : ''}`}
                  rows={3}
                  disabled={isSaving || !canEdit}
                />
                <small className={styles.fieldHint}>
                  Internal notes are not public. Mention equipment needs (e.g., laptops, projector, laser cutter).
                </small>
              </div>

              <div className={styles.formGroup}>
                <label htmlFor="proposal-duration-days" className={styles.label}>
                  Number of Days
                  {changedFields.has('duration_days') && <span className={styles.changedIndicator} aria-label="unsaved change">●</span>}
                </label>
                <input
                  id="proposal-duration-days"
                  type="number"
                  min="1"
                  value={formData.duration_days}
                  onChange={(e) => handleFieldChange('duration_days', parseInt(e.target.value) || 1)}
                  className={`${styles.input} ${changedFields.has('duration_days') ? styles.changed : ''}`}
                  disabled={isSaving || !canEdit}
                  required
                />
                <small className={styles.fieldHint}>
                  Number of days for the event (minimum 1).
                </small>
              </div>

              <div className={styles.formGroup}>
                <label htmlFor="proposal-duration-time" className={styles.label}>
                  Time per Day (HH:MM or minutes)
                  {changedFields.has('duration_time_per_day') && <span className={styles.changedIndicator} aria-label="unsaved change">●</span>}
                </label>
                <input
                  id="proposal-duration-time"
                  type="text"
                  placeholder="HH:MM"
                  value={formData.duration_time_per_day}
                  onChange={(e) => {
                    let value = e.target.value
                    value = value.replace(/[^\d:]/g, '')
                    const parts = value.split(':')
                    if (parts.length > 2) {
                      value = `${parts[0]}:${parts[1]}`
                    }
                    handleFieldChange('duration_time_per_day', value)
                  }}
                  className={`${styles.input} ${changedFields.has('duration_time_per_day') ? styles.changed : ''}`}
                  disabled={isSaving || !canEdit}
                  required
                  maxLength={5}
                />
                <small className={styles.fieldHint}>
                  Time per day in HH:MM format. Product of days and time should be greater than zero. (Example: 08:30 for 8 hours 30 minutes)
                </small>
              </div>

              <div className={styles.formGroup}>
                <label htmlFor="proposal-occurrence-count" className={styles.label}>
                  How often would you offer this event?
                  {changedFields.has('occurrence_count') && <span className={styles.changedIndicator} aria-label="unsaved change">●</span>}
                </label>
                <input
                  id="proposal-occurrence-count"
                  type="number"
                  value={formData.occurrence_count}
                  onChange={(e) => handleFieldChange('occurrence_count', parseInt(e.target.value) || 0)}
                  className={`${styles.input} ${changedFields.has('occurrence_count') ? styles.changed : ''}`}
                  disabled={isSaving || !canEdit}
                  required
                />
              </div>
          </div>
        </details>

        {/* Additional Information Section */}
        <details
          className={styles.fieldset}
          name="proposal-editor-sections"
        >
          <summary className={styles.legend}>
            <span className={styles.summaryContent}>Additional Information</span>
          </summary>

          <div className={styles.detailsContent}>
              <div className={styles.formGroup}>
                <label className={styles.label}>
                  <input
                    id="proposal-is-basic-course"
                    type="checkbox"
                    checked={formData.is_basic_course}
                    onChange={(e) => handleFieldChange('is_basic_course', e.target.checked)}
                    disabled={isSaving || !canEdit}
                    aria-describedby="proposal-is-basic-course-desc"
                  />
                  This workshop is a basic course
                </label>

                <small id="proposal-is-basic-course-desc" className={styles.fieldHint} style={{ marginBottom: '0.75rem' }}>
                  A basic course is a course which is mandatory for using certain resources, such as machines or rooms.
                </small>
              </div>

              <div className={styles.formGroup}>
                <label htmlFor="proposal-max-participants" className={styles.label}>
                  Max. Number of Participants
                  {changedFields.has('max_participants') && <span className={styles.changedIndicator} aria-label="unsaved change">●</span>}
                </label>
                <input
                  id="proposal-max-participants"
                  type="number"
                  value={formData.max_participants}
                  onChange={(e) => handleFieldChange('max_participants', parseInt(e.target.value) || 0)}
                  className={`${styles.input} ${changedFields.has('max_participants') ? styles.changed : ''}`}
                  disabled={isSaving || !canEdit}
                  required
                />
              </div>

              <div className={styles.formGroup}>
                <label htmlFor="proposal-material-cost" className={styles.label}>
                  Material Cost per Participant (EUR)
                  {changedFields.has('material_cost_eur') && <span className={styles.changedIndicator} aria-label="unsaved change">●</span>}
                </label>
                <input
                  id="proposal-material-cost"
                  type="number"
                  step="0.01"
                  value={formData.material_cost_eur}
                  onChange={(e) => handleFieldChange('material_cost_eur', e.target.value)}
                  className={`${styles.input} ${changedFields.has('material_cost_eur') ? styles.changed : ''}`}
                  disabled={isSaving || !canEdit}
                  required
                />
              </div>

              <div className={styles.formGroup}>
                <label htmlFor="proposal-preferred-dates" className={styles.label}>
                  Preferred Date and Alternatives
                  {changedFields.has('preferred_dates') && <span className={styles.changedIndicator} aria-label="unsaved change">●</span>}
                </label>
                <textarea
                  id="proposal-preferred-dates"
                  value={formData.preferred_dates}
                  onChange={(e) => handleFieldChange('preferred_dates', e.target.value)}
                  className={`${styles.textarea} ${changedFields.has('preferred_dates') ? styles.changed : ''}`}
                  rows={3}
                  disabled={isSaving || !canEdit}
                  required
                />
                <small className={styles.fieldHint}>
                  Please enter specific dates and times that work for you.
                </small>
              </div>
          </div>
        </details>

        {/* Profile Section */}
        <details
          className={styles.fieldset}
          name="proposal-editor-sections"
        >
          <summary className={styles.legend}>
            <span className={styles.summaryContent}>About Yourself</span>
          </summary>

          <div className={styles.detailsContent}>
              <div className={styles.formGroup}>
                <label className={styles.label}>
                  <input
                    id="proposal-is-regular-member"
                    type="checkbox"
                    checked={formData.is_regular_member}
                    onChange={(e) => handleFieldChange('is_regular_member', e.target.checked)}
                    disabled={isSaving || !canEdit}
                  />
                  Are you a regular member?
                </label>
              </div>

              <div className={styles.formGroup}>
                <label className={styles.label}>
                  <input
                    id="proposal-has-building-access"
                    type="checkbox"
                    checked={formData.has_building_access}
                    onChange={(e) => handleFieldChange('has_building_access', e.target.checked)}
                    disabled={isSaving || !canEdit}
                  />
                  Do you have ZAM-building access?
                </label>
              </div>

              <div className={styles.formGroup}>
                <label className={styles.label} id="proposal-owner-label">Owner</label>
                <div className={styles.ownerDisplay} aria-labelledby="proposal-owner-label">
                  {owner ? (
                    <span>{owner.username}</span>
                  ) : (
                    <span style={{ fontStyle: 'italic' }}>Owner will be set automatically when proposal is created</span>
                  )}
                </div>
                <small className={styles.fieldHint}>
                  The owner is automatically set to the user who creates the proposal and cannot be changed.
                </small>
              </div>

              <div className={styles.formGroup}>
                <label htmlFor="proposal-editors-search" className={styles.label}>
                  Editors
                  {changedFields.has('editors') && <span className={styles.changedIndicator} aria-label="unsaved change">●</span>}
                </label>
                <small className={styles.fieldHint} style={{ marginBottom: '0.75rem' }}>
                  Editors can view and modify this proposal. Add users who should be able to edit the proposal content.
                </small>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  <input
                    id="proposal-editors-search"
                    type="text"
                    list="proposal-editor-list"
                    placeholder="Search and add editors..."
                    value={participantSearchQuery}
                    onChange={(e) => {
                      const newValue = e.target.value
                      setParticipantSearchQuery(newValue)
                      const selectedUser = participantSearchResults.find((u) => u.username === newValue)
                      if (selectedUser && !editors.find((p) => p.id === selectedUser.id)) {
                        setEditors((prev) => [...prev, selectedUser])
                        setChangedFields((prev) => new Set(prev).add('editors'))
                        setError(null)
                        setParticipantSearchQuery('')
                      }
                    }}
                    className={`${styles.input} ${changedFields.has('editors') ? styles.changed : ''}`}
                    disabled={isSaving || !canEdit}
                  />
                  <datalist id="proposal-editor-list">
                    {participantSearchResults
                      .filter((u) => !editors.find((p) => p.id === u.id))
                      .map((user) => (
                        <option key={user.id} value={user.username} />
                      ))}
                  </datalist>

                  {editors.length > 0 && (
                    <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                      {editors.map((p) => (
                        <span
                          key={p.id}
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '0.4rem',
                            backgroundColor: '#e3f2fd',
                            color: '#1565c0',
                            borderRadius: '999px',
                            padding: '0.3rem 0.6rem',
                            fontSize: '0.85rem',
                          }}
                        >
                          {p.username}
                          <button
                            type="button"
                            onClick={() => handleRemoveEditor(p.id)}
                            disabled={isSaving || !canEdit}
                            style={{
                              border: 'none',
                              background: 'transparent',
                              color: '#1565c0',
                              cursor: 'pointer',
                              padding: 0,
                              fontSize: '0.9rem',
                              lineHeight: 1,
                            }}
                            aria-label={`Remove ${p.username}`}
                          >
                            ×
                          </button>
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                <small className={styles.fieldHint} style={{ marginBottom: '0.75rem' }}>
                  Editors can view and modify this proposal. Add users who should be able to edit the proposal content.
                </small>
              </div>

              {/* Speaker list editor */}
              <div style={{ marginTop: '1rem' }}>
                <SpeakerListEditor
                  proposalId={_proposalId ?? ''}
                  speakers={speakers}
                  onSpeakersChange={async (newSpeakers) => {
                    setSpeakers(newSpeakers)
                    // Refresh checklist when speakers change
                    if (_proposalId && _proposalId.trim()) {
                      try {
                        setChecklistLoading(true)
                        const data = await fetchProposalChecklist(_proposalId)
                        setChecklist(data)
                      } catch (err) {
                        console.error('Failed to refresh checklist after speaker change:', err)
                      } finally {
                        setChecklistLoading(false)
                      }
                    }
                  }}
                  disabled={isSaving || !_proposalId || !_proposalId.trim() || !canEdit}
                />
              </div>
          </div>
        </details>

        {error && <div className={styles.error} role="alert">{error}</div>}

        <div className={styles.buttonGroup}>
          <button type="button" onClick={handleSave} disabled={!hasChanges || isSaving} className={styles.saveButton} aria-busy={isSaving}>
            {isSaving ? 'Saving...' : 'Save Proposal'}
          </button>
          {hasChanges && (
            <button type="button" onClick={handleCancel} disabled={isSaving || !canEdit} className={styles.cancelButton}>
              Cancel
            </button>
          )}
        </div>
      </form>

      {/* Checklist Display - Moved to bottom */}
      {_proposalId && _proposalId.trim() && (
        <div className={styles.checklistBox}>
          <h3>Submission Checklist</h3>
          {checklistLoading ? (
            <p className={styles.checklistMuted}>Loading checklist...</p>
          ) : Object.keys(checklist).length === 0 ? (
            <p className={styles.checklistMuted}>Save the proposal to see the checklist</p>
          ) : (
            <ul style={{ margin: 0, padding: 0, listStyle: 'none' }}>
              {Object.entries(checklist).map(([item, { status }]) => (
                <li
                  key={item}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.5rem',
                    padding: '0.4rem 0',
                    fontSize: '0.9rem',
                  }}
                >
                  <span
                    style={{
                      display: 'inline-block',
                      width: '1.2rem',
                      fontSize: '1.2rem',
                      lineHeight: '1',
                      color: status === 'ok' ? '#4caf50' : '#ff9800',
                      fontWeight: 'bold',
                      flexShrink: 0,
                    }}
                    title={status === 'ok' ? 'Complete' : 'Incomplete'}
                  >
                    {status === 'ok' ? '✓' : '⚠'}
                  </span>
                  <span className={status === 'ok' ? styles['checklistItemText--ok'] : styles['checklistItemText--warn']}>{item}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* History Display - Moved to bottom */}
      {_proposalId && _proposalId.trim() && (
        <details
          className={styles.fieldset}
          style={{ marginTop: '2rem' }}
        >
          <summary className={`${styles.legend} ${styles.historySummary}`}>
            <span className={`${styles.summaryContent} ${styles.historySummary}`}>
              <span>Edit history</span>
              <span className={styles.historyBadge}>
                {historyBadge}
              </span>
            </span>
          </summary>

          <div className={styles.detailsContent} style={{ marginTop: '0.25rem' }}>
              {historyLoading ? (
                <p className={styles.historyMuted}>Loading history...</p>
              ) : history.length === 0 ? (
                <p className={styles.historyMuted}>No changes recorded in the last 7 days</p>
              ) : (
                <ul style={{ margin: 0, padding: 0, listStyle: 'none' }}>
                  {history.map((entry, index) => (
                    <li
                      key={index}
                      className={index < history.length - 1 ? styles.historyEntry : undefined}
                      style={{
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '0.45rem',
                        padding: '0.7rem 0',
                        fontSize: '0.9rem',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <span
                          style={{
                            display: 'inline-block',
                            width: '6px',
                            height: '6px',
                            borderRadius: '50%',
                            backgroundColor:
                              entry.change_type === 'create'
                                ? '#4caf50'
                                : entry.change_type === 'change'
                                  ? '#2196f3'
                                  : '#ff9800',
                            flexShrink: 0,
                          }}
                        />
                        <span className={styles.historyEntrySummary}>{entry.summary}</span>
                      </div>

                      <div className={styles.historyEntryMeta} style={{ paddingLeft: '1rem' }}>
                        <div>
                          By: <strong>{entry.changed_by}</strong>
                        </div>
                        <div>
                          {formatLocalIso(entry.timestamp)} ({formatRelativeTime(entry.timestamp)})
                        </div>
                        {entry.field_name && (
                          <div style={{ marginTop: '0.2rem' }}>
                            <span style={{ fontStyle: 'italic' }}>Field:</span> {entry.field_name}
                          </div>
                        )}

                        {(entry.old_value !== undefined && entry.old_value !== null) ||
                        (entry.new_value !== undefined && entry.new_value !== null) ? (
                          <div
                            style={{
                              marginTop: '0.35rem',
                              display: 'grid',
                              gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
                              gap: '0.4rem',
                            }}
                          >
                            {entry.old_value !== undefined && entry.old_value !== null && (
                              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
                                <span className={styles['historyValueLabel--old']}>Old</span>
                                <div className={styles['historyValueBox--old']}>
                                  {entry.old_value}
                                </div>
                              </div>
                            )}
                            {entry.new_value !== undefined && entry.new_value !== null && (
                              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
                                <span className={styles['historyValueLabel--new']}>New</span>
                                <div className={styles['historyValueBox--new']}>
                                  {entry.new_value}
                                </div>
                              </div>
                            )}
                          </div>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
          </div>
        </details>
      )}

      {/* Transition Buttons - Below history */}
      {_proposalId && _proposalId.trim() && (
        <ProposalTransitionButtons
          proposalId={_proposalId}
          onTransitionSuccess={(updatedProposal) => {
            // Reload form data with updated proposal
            setFormData({
              title: updatedProposal.title,
              submission_type: updatedProposal.submission_type,
              area: updatedProposal.area || '',
              language: updatedProposal.language || '',
              abstract: updatedProposal.abstract,
              description: updatedProposal.description,
              internal_notes: updatedProposal.internal_notes,
              occurrence_count: updatedProposal.occurrence_count,
              duration_days: updatedProposal.duration_days,
              duration_time_per_day: updatedProposal.duration_time_per_day,
              is_basic_course: updatedProposal.is_basic_course,
              max_participants: updatedProposal.max_participants,
              material_cost_eur: updatedProposal.material_cost_eur,
              preferred_dates: updatedProposal.preferred_dates,
              is_regular_member: updatedProposal.is_regular_member,
              has_building_access: updatedProposal.has_building_access,
            })
            // Reload history to show the status change
            if (_proposalId && _proposalId.trim()) {
              const loadHistory = async () => {
                try {
                  setHistoryLoading(true)
                  const data = await fetchProposalHistory(_proposalId, 7)
                  setHistory(data.entries)
                } catch (err) {
                  console.error('Failed to reload history:', err)
                }
              }
              loadHistory()
              // Reload status
              fetchProposalTransitions(_proposalId).then((data) => {
                setCurrentStatus(data.current_status)
              }).catch(console.error)
            }
          }}
          onTransitionError={(error) => {
            console.error('Transition error:', error)
          }}
        />
      )}

      {/* Linked Events Section */}
      {_proposalId && _proposalId.trim() && currentStatus === 'accepted' && (
        <details
          className={styles.fieldset}
          style={{ marginTop: '1.5rem' }}
          open={true}
        >
          <summary className={styles.legend}>
            <span className={styles.summaryContent}>
              Linked Events ({linkedEvents.length})
            </span>
          </summary>
          <div className={styles.detailsContent}>
            {linkedEventsLoading ? (
              <p style={{ color: '#888', fontSize: '0.9rem' }}>Loading linked events...</p>
            ) : linkedEvents.length === 0 ? (
              <p style={{ color: '#888', fontSize: '0.9rem' }}>No events linked to this proposal yet.</p>
            ) : (
              <ul style={{ margin: 0, padding: 0, listStyle: 'none' }}>
                {linkedEvents.map((ev) => (
                  <li key={ev.id} style={{ padding: '0.5rem 0', borderBottom: '1px solid #eee' }}>
                    <Link
                      to={`/proposal/${_proposalId}/event/${ev.id}`}
                      style={{ color: '#1976d2', textDecoration: 'none', fontWeight: 500 }}
                    >
                      {ev.name}
                    </Link>
                    <div style={{ fontSize: '0.8rem', color: '#666' }}>
                      Series: {ev.series_name}
                    </div>
                    <div style={{ fontSize: '0.8rem', color: '#666' }}>
                      {new Date(ev.startTime).toLocaleDateString('de-DE', {
                        year: 'numeric',
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                      {' – '}
                      {new Date(ev.endTime).toLocaleDateString('de-DE', {
                        year: 'numeric',
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </div>
                  </li>
                ))}
              </ul>
            )}
            <div style={{ marginTop: '1rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <div>
                <label htmlFor="create-event-series-filter" style={{ display: 'block', fontSize: '0.85rem', fontWeight: 500, marginBottom: '0.3rem' }}>
                  Series
                </label>
                <input
                  id="create-event-series-filter"
                  type="text"
                  placeholder="Filter series..."
                  value={seriesSearchQuery}
                  onChange={(e) => {
                    setSeriesSearchQuery(e.target.value)
                    setSelectedSeriesId('')
                  }}
                  style={{ width: '100%', padding: '0.5rem', border: '1px solid #ccc', borderRadius: '4px', fontSize: '0.9rem', boxSizing: 'border-box' }}
                />
              </div>
              <select
                id="create-event-series-select"
                aria-label="Series"
                value={selectedSeriesId}
                onChange={(e) => setSelectedSeriesId(e.target.value)}
                style={{ width: '100%', padding: '0.5rem', border: '1px solid #ccc', borderRadius: '4px', fontSize: '0.9rem' }}
              >
                <option value="">-- Select a series --</option>
                {seriesSearchResults.map((s) => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
              <button
                type="button"
                onClick={handleCreateEvent}
                disabled={!selectedSeriesId || isCreatingEvent}
                style={{
                  padding: '0.5rem 1.2rem',
                  backgroundColor: '#4caf50',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: !selectedSeriesId || isCreatingEvent ? 'not-allowed' : 'pointer',
                  fontWeight: 600,
                  fontSize: '0.9rem',
                  opacity: !selectedSeriesId || isCreatingEvent ? 0.6 : 1,
                  alignSelf: 'flex-start',
                }}
              >
                {isCreatingEvent ? 'Creating...' : 'Create New Event'}
              </button>
              {createEventError && (
                <div style={{ color: '#d32f2f', fontSize: '0.85rem', marginTop: '0.3rem' }}>{createEventError}</div>
              )}
            </div>
          </div>
        </details>
      )}
    </div>
  )
}


