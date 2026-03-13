import createClient from 'openapi-fetch'
import type { paths } from './schema'

const CSRF_COOKIE_NAME = 'csrftoken'
const CSRF_HEADER_NAME = 'X-CSRFToken'

let csrfToken: string | null = null

// Helper to extract CSRF token from cookies
function getCsrfTokenFromCookie(): string | null {
  if (typeof document === 'undefined') return null

  const value = `; ${document.cookie}`
  const parts = value.split(`; ${CSRF_COOKIE_NAME}=`)
  if (parts.length === 2) {
    return parts.pop()?.split(';').shift() || null
  }
  return null
}

// Fetch and cache CSRF token
export async function initializeCsrfToken(): Promise<string> {
  try {
    const response = await fetch('/api/v1/csrf', {
      method: 'GET',
      credentials: 'include',
    })

    if (response.ok) {
      csrfToken = getCsrfTokenFromCookie()
      if (!csrfToken) {
        console.warn('CSRF token cookie not found after CSRF endpoint call')
      }
    }
  } catch (error) {
    console.error('Failed to initialize CSRF token:', error)
  }

  return csrfToken || ''
}

// Get the current CSRF token (or fetch it if not yet initialized)
export async function getCsrfToken(): Promise<string> {
  // Django can rotate CSRF (for example on login), so prefer current cookie.
  const tokenFromCookie = getCsrfTokenFromCookie()
  if (tokenFromCookie) {
    csrfToken = tokenFromCookie
  } else if (!csrfToken) {
    csrfToken = await initializeCsrfToken()
  }
  return csrfToken || ''
}

const client = createClient<paths>({
  baseUrl: '',
  fetch: async (request: Request) => {
    // Ensure CSRF token is initialized
    const token = await getCsrfToken()

    // Add CSRF token to POST, PUT, PATCH, DELETE requests
    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(request.method)) {
      // Clone request to modify headers
      const headers = new Headers(request.headers)
      if (token) {
        headers.set(CSRF_HEADER_NAME, token)
      }

      const modifiedRequest = new Request(request, {
        headers,
        credentials: 'include',
      })

      return fetch(modifiedRequest)
    }

    // For GET and other safe methods, just ensure credentials
    const safeRequest = new Request(request, {
      credentials: 'include',
    })

    return fetch(safeRequest)
  },
})

// Authentication Types
export interface User {
  username: string
  user_id: string
}

export interface UserBasic {
  id: string
  username: string
}

export interface AuthError {
  error: string
}

export interface UserPermissions {
  is_authenticated: boolean
  is_staff: boolean
  is_superuser: boolean
  is_active: boolean
  permissions: string[]
}

export interface PermissionCheckRequest {
  app: string
  action: 'view' | 'add' | 'change' | 'delete' | 'browse'
  object_type: string
  object_id?: string
}

interface ApiEvent {
  id: string
  name: string
  startTime: string
  endTime: string
  tag?: string
  useFullDays?: boolean
  proposal_id?: string | null
  series_id?: string | null
  series_name?: string | null
}

interface ApiSeries {
  id: string
  name: string
  description?: string
  events: ApiEvent[]
}

interface ApiSeriesListItem {
  id: string
  name: string
  description?: string
}

interface ApiCreateEventResponse {
  series_id: string
  event: ApiEvent
}

type SeriesApiResponse = paths['/api/v1/series']['get']['responses'][200] extends {
  content: { 'application/json': infer T }
}
  ? T
  : ApiSeriesListItem[]

// Frontend types (converted to Date objects)
export interface Event {
  id: string
  name: string
  startTime: Date
  endTime: Date
  tag?: string
  useFullDays?: boolean
  proposal_id?: string | null
  series_id?: string | null
  series_name?: string | null
  [key: string]: unknown
}

export interface Series {
  id: string
  name: string
  description?: string
  events: Event[]
}

function toFrontendSeries(data: ApiSeries[]): Series[] {
  return data.map((series) => ({
    ...series,
    events: series.events.map((event) => ({
      ...event,
      startTime: new Date(event.startTime),
      endTime: new Date(event.endTime),
    })),
  }))
}

function toFrontendSeriesItem(series: ApiSeries): Series {
  return toFrontendSeries([series])[0]
}

function toFrontendEvent(event: ApiEvent): Event {
  return {
    ...event,
    startTime: new Date(event.startTime),
    endTime: new Date(event.endTime),
  }
}

async function fetchCalendarData(): Promise<Series[]> {
  const { data, error, response } = await client.GET('/api/v1/series')

  if (error || !response.ok) {
    throw new Error(`Failed to fetch calendar data: ${response.statusText}`)
  }

  const apiData = (data ?? []) as SeriesApiResponse
  return (apiData as ApiSeriesListItem[]).map((series) => ({
    id: series.id,
    name: series.name,
    description: series.description,
    events: [],
  }))
}

export async function fetchSeriesById(seriesId: string): Promise<Series> {
  const { data, error, response } = await client.GET('/api/v1/series/{series_id}', {
    params: {
      path: {
        series_id: seriesId,
      },
    },
  })

  if (error || !response.ok || !data) {
    throw new Error(`Failed to fetch series details: ${response.statusText}`)
  }

  return toFrontendSeriesItem(data as unknown as ApiSeries)
}

export async function loadSeriesFromAPI(): Promise<Series[]> {
  try {
    return await fetchCalendarData()
  } catch (error) {
    console.error('Error loading series from API:', error)
    throw error
  }
}

// Sync Status Types (fallback DTOs since schema has content?: never)
export interface SyncStatus {
  platform: string
  status: 'no entry exists' | 'entry up-to-date' | 'entry differs'
  last_synced?: string
  last_error?: string
}

export interface EventSyncInfo {
  series_id: string
  event_id: string
  sync_statuses: SyncStatus[]
}

export interface SyncPushResult {
  success: boolean
  message: string
  timestamp: string
  platform: string
  series_id: string
  event_id: string
}

export interface PropertyDiff {
  property_name: string
  local_value: string
  remote_value: string
  file_type: string
}

export interface SyncDiffData {
  series_id: string
  event_id: string
  platform: string
  properties: PropertyDiff[]
}

export interface ProposalSummary {
  id: string
  title: string
  submission_type: string
}

export async function fetchSyncStatus(
  seriesId: string,
  eventId: string
): Promise<EventSyncInfo> {
  const { data, error, response } = await client.GET(
    '/api/v1/sync/status/{series_id}/{event_id}',
    {
      params: {
        path: {
          series_id: seriesId,
          event_id: eventId,
        },
      },
    }
  )

  if (error || !response.ok) {
    throw new Error(`Failed to fetch sync status: ${response.statusText}`)
  }

  // Cast since schema has content?: never but backend returns JSON
  return data as unknown as EventSyncInfo
}

export async function pushToPlatform(
  seriesId: string,
  eventId: string,
  platform: string
): Promise<SyncPushResult> {
  const { data, error, response } = await client.POST(
    '/api/v1/sync/push/{series_id}/{event_id}/{platform}',
    {
      params: {
        path: {
          series_id: seriesId,
          event_id: eventId,
          platform: platform,
        },
      },
    }
  )

  if (error || !response.ok) {
    throw new Error(`Failed to push to platform: ${response.statusText}`)
  }

  // Cast since schema has content?: never but backend returns JSON
  return data as unknown as SyncPushResult
}

export async function fetchSyncDiff(
  seriesId: string,
  eventId: string,
  platform: string
): Promise<SyncDiffData> {
  const { data, error, response } = await client.GET(
    '/api/v1/sync/diff/{series_id}/{event_id}/{platform}',
    {
      params: {
        path: {
          series_id: seriesId,
          event_id: eventId,
          platform: platform,
        },
      },
    }
  )

  if (error || !response.ok) {
    throw new Error(`Failed to fetch sync diff: ${response.statusText}`)
  }

  // Cast since schema has content?: never but backend returns JSON
  return data as unknown as SyncDiffData
}

// Authentication API functions
export async function login(username: string, password: string): Promise<User> {
  const { data, error, response } = await client.POST('/api/v1/authenticate', {
    body: {
      username,
      password,
    },
  })

  if (error || !response.ok) {
    const errorData = data as unknown as AuthError
    throw new Error(errorData?.error || `Login failed: ${response.statusText}`)
  }

  // Ensure subsequent state-changing requests use the post-login CSRF token.
  csrfToken = getCsrfTokenFromCookie() || (await initializeCsrfToken())

  return data as unknown as User
}

export async function getCurrentUser(): Promise<User> {
  const { data, error, response } = await client.GET('/api/v1/me')

  if (error || !response.ok) {
    if (response.status === 401) {
      return null as unknown as User
    }

    throw new Error(error?.error || 'Failed to get current user')
  }

  return data as unknown as User
}

export async function getUserPermissions(): Promise<UserPermissions> {
  const { data, error, response } = await client.GET('/api/v1/user/permissions')

  if (error || !response.ok) {
    if (response.status === 401) {
      return {
        is_authenticated: false,
        is_staff: false,
        is_superuser: false,
        is_active: false,
        permissions: [],
      }
    }

    throw new Error(error?.error || 'Failed to get user permissions')
  }

  return data as unknown as UserPermissions
}

export async function checkObjectPermission(request: PermissionCheckRequest): Promise<boolean> {
  const { error, response } = await client.POST('/api/v1/user/permission', {
    body: {
      app: request.app,
      action: request.action,
      object_type: request.object_type,
      object_id: request.object_id,
    },
  })

  if (response?.ok) {
    return true
  }

  if (response?.status === 401 || response?.status === 403 || response?.status === 400) {
    return false
  }

  if (error) {
    console.error('Permission check failed:', error)
  }
  return false
}

export async function logout(): Promise<void> {
  const { response } = await client.POST('/api/v1/logout', {})

  if (!response.ok) {
    throw new Error('Logout failed')
  }
}

// Series and Event API functions
export interface CreateSeriesRequest {
  name?: string
  description?: string
}

export async function createSeries(request: CreateSeriesRequest = {}): Promise<Series> {
  const { data, error, response } = await client.POST('/api/v1/series/create', {
    body: request,
  })

  if (error || !response.ok || !data) {
    throw new Error(`Failed to create series: ${response.statusText}`)
  }

  return toFrontendSeriesItem(data as unknown as ApiSeries)
}

export interface CreateEventRequest {
  seriesId: string
  name?: string
  startTime?: string
  endTime?: string
  tag?: string
  proposal_id?: string
}

export async function createEvent(request: CreateEventRequest): Promise<Event> {
  const { data, error, response } = await client.POST('/api/v1/series/{series_id}/events/create', {
    params: {
      path: {
        series_id: request.seriesId,
      },
    },
    body: {
      name: request.name,
      startTime: request.startTime,
      endTime: request.endTime,
      tag: request.tag,
      proposal_id: request.proposal_id,
    },
  })

  if (error || !response.ok || !data) {
    throw new Error(`Failed to create event: ${response.statusText}`)
  }

  const payload = data as unknown as ApiCreateEventResponse
  return toFrontendEvent(payload.event)
}

export interface UpdateSeriesRequest {
  seriesId: string
  name?: string
  description?: string
}

export async function updateSeries(request: UpdateSeriesRequest): Promise<Series> {
  const { data, error, response } = await client.PUT('/api/v1/series/{series_id}', {
    params: {
      path: {
        series_id: request.seriesId,
      },
    },
    body: {
      name: request.name,
      description: request.description,
    },
  })

  if (error || !response.ok || !data) {
    throw new Error(`Failed to update series: ${response.statusText}`)
  }

  return toFrontendSeriesItem(data as unknown as ApiSeries)
}

export async function deleteSeries(seriesId: string): Promise<void> {
  const { error, response } = await client.DELETE('/api/v1/series/{series_id}', {
    params: {
      path: {
        series_id: seriesId,
      },
    },
  })

  if (error || !response.ok) {
    throw new Error(error?.error || `Failed to delete series: ${response.statusText}`)
  }
}

export interface UpdateEventRequest {
  seriesId: string
  eventId: string
  name?: string
  startTime?: string
  endTime?: string
  tag?: string | null
  useFullDays?: boolean
  proposal_id?: string | null
  series_id?: string | null
}

export async function updateEvent(request: UpdateEventRequest): Promise<Event> {
  const { data, error, response } = await client.PUT('/api/v1/series/{series_id}/events/{event_id}', {
    params: {
      path: {
        series_id: request.seriesId,
        event_id: request.eventId,
      },
    },
    body: {
      name: request.name,
      startTime: request.startTime,
      endTime: request.endTime,
      tag: request.tag,
      useFullDays: request.useFullDays,
      proposal_id: request.proposal_id,
      series_id: request.series_id,
    },
  })

  if (error || !response.ok || !data) {
    throw new Error(`Failed to update event: ${response.statusText}`)
  }

  return toFrontendEvent(data as unknown as ApiEvent)
}

export async function deleteEvent(seriesId: string, eventId: string): Promise<void> {
  const { error, response } = await client.DELETE('/api/v1/series/{series_id}/events/{event_id}', {
    params: {
      path: {
        series_id: seriesId,
        event_id: eventId,
      },
    },
  })

  if (error || !response.ok) {
    throw new Error(error?.error || `Failed to delete event: ${response.statusText}`)
  }
}

export async function searchUsers(query: string = ''): Promise<UserBasic[]> {
  const { data, error, response } = await client.GET('/api/v1/users/search', {
    params: {
      query: {
        q: query,
      },
    },
  })

  if (error || !response.ok) {
    console.error('Failed to search users:', response.statusText)
    return []
  }

  return (data as unknown as UserBasic[]) || []
}

export async function searchProposals(query: string = ''): Promise<ProposalSummary[]> {
  const { data, error, response } = await client.GET('/api/v1/proposals/search', {
    params: {
      query: {
        q: query,
      },
    },
  })

  if (error || !response.ok) {
    console.error('Failed to search proposals:', response.statusText)
    return []
  }

  return (data as unknown as ProposalSummary[]) || []
}

export async function searchSeriesAutocomplete(query: string = ''): Promise<Series[]> {
  const { data, error, response } = await client.GET('/api/v1/series/search', {
    params: {
      query: {
        q: query,
      },
    },
  })

  if (error || !response.ok) {
    console.error('Failed to search series:', response.statusText)
    return []
  }

  return toFrontendSeries((data as unknown as ApiSeries[]) || [])
}

export async function searchEventsAutocomplete(
  query: string = '',
  seriesId?: string
): Promise<Event[]> {
  const { data, error, response } = await client.GET('/api/v1/events/search', {
    params: {
      query: {
        q: query,
        series_id: seriesId,
      },
    },
  })

  if (error || !response.ok) {
    console.error('Failed to search events:', response.statusText)
    return []
  }

  return ((data as unknown as ApiEvent[]) || []).map(toFrontendEvent)
}

export async function fetchProposalChecklist(proposalId: string): Promise<Record<string, ProposalChecklistItem>> {
  const { data, error, response } = await client.GET('/api/v1/proposals/{proposal_id}/checklist', {
    params: {
      path: {
        proposal_id: proposalId,
      },
    },
  })

  if (error || !response.ok || !data) {
    throw new Error(`Failed to fetch proposal checklist: ${response.statusText}`)
  }

  return data as unknown as Record<string, ProposalChecklistItem>
}

export async function fetchProposalHistory(proposalId: string, days: number = 7): Promise<ProposalHistory> {
  const { data, error, response } = await client.GET('/api/v1/proposals/{proposal_id}/history', {
    params: {
      path: {
        proposal_id: proposalId,
      },
      query: {
        days,
      },
    },
  })

  if (error || !response.ok || !data) {
    throw new Error(`Failed to fetch proposal history: ${response.statusText}`)
  }

  return data as unknown as ProposalHistory
}

export interface ProposalTransition {
  action: string  // 'submit', 'accept', 'reject', 'revise'
  label: string  // human-readable label
  target_status: string  // target status
  enabled: boolean  // whether the transition is currently allowed
  disable_reason?: string | null  // reason if disabled
}

export interface ProposalTransitions {
  proposal_id: string
  current_status: string
  transitions: ProposalTransition[]
}

export async function fetchProposalTransitions(proposalId: string): Promise<ProposalTransitions> {
  const { data, error, response } = await client.GET('/api/v1/proposals/{proposal_id}/transitions', {
    params: {
      path: {
        proposal_id: proposalId,
      },
    },
  })

  if (error || !response.ok || !data) {
    throw new Error(`Failed to fetch proposal transitions: ${response.statusText}`)
  }

  return data as unknown as ProposalTransitions
}

export async function submitProposal(proposalId: string): Promise<ProposalDetail> {
  const { data, error, response } = await client.POST('/api/v1/proposals/{proposal_id}/submit', {
    params: {
      path: {
        proposal_id: proposalId,
      },
    },
  })

  if (error || !response.ok || !data) {
    throw new Error(`Failed to submit proposal: ${response.statusText}`)
  }

  return data as unknown as ProposalDetail
}

export async function acceptProposal(proposalId: string): Promise<ProposalDetail> {
  const { data, error, response } = await client.POST('/api/v1/proposals/{proposal_id}/accept', {
    params: {
      path: {
        proposal_id: proposalId,
      },
    },
  })

  if (error || !response.ok || !data) {
    throw new Error(`Failed to accept proposal: ${response.statusText}`)
  }

  return data as unknown as ProposalDetail
}

export async function rejectProposal(proposalId: string): Promise<ProposalDetail> {
  const { data, error, response } = await client.POST('/api/v1/proposals/{proposal_id}/reject', {
    params: {
      path: {
        proposal_id: proposalId,
      },
    },
  })

  if (error || !response.ok || !data) {
    throw new Error(`Failed to reject proposal: ${response.statusText}`)
  }

  return data as unknown as ProposalDetail
}

export async function reviseProposal(proposalId: string): Promise<ProposalDetail> {
  const { data, error, response } = await client.POST('/api/v1/proposals/{proposal_id}/revise', {
    params: {
      path: {
        proposal_id: proposalId,
      },
    },
  })

  if (error || !response.ok || !data) {
    throw new Error(`Failed to revise proposal: ${response.statusText}`)
  }

  return data as unknown as ProposalDetail
}

export async function createProposal(formData?: {
  title?: string
  submission_type?: string
  area?: string
  language?: string
  abstract?: string
  description?: string
  internal_notes?: string
  occurrence_count?: number
  duration_days?: number
  duration_time_per_day?: string
  is_basic_course?: boolean
  max_participants?: number
  material_cost_eur?: string
  preferred_dates?: string
  is_regular_member?: boolean
  has_building_access?: boolean
}): Promise<ProposalSummary> {
  const { data, error, response } = await client.POST('/api/v1/proposals/create', {
    body: formData || {},
  })

  if (error || !response.ok || !data) {
    throw new Error(`Failed to create proposal: ${response.statusText}`)
  }

  return data as unknown as ProposalSummary
}

export async function deleteProposal(proposalId: string): Promise<void> {
  const { error, response } = await client.DELETE('/api/v1/proposals/{proposal_id}', {
    params: {
      path: {
        proposal_id: proposalId,
      },
    },
  })

  if (error || !response.ok) {
    throw new Error(error?.error || `Failed to delete proposal: ${response.statusText}`)
  }
}

export interface ProposalChecklistItem {
  status: 'ok' | 'error'
}

export interface ProposalHistoryEntry {
  timestamp: string  // ISO format datetime
  changed_by: string  // username of user who made the change
  change_type: string  // 'create', 'change', 'delete'
  field_name?: string | null  // which field was changed
  old_value?: string | null  // previous value
  new_value?: string | null  // new value
  summary: string  // human-readable summary of the change
}

export interface ProposalHistory {
  proposal_id: string
  entries: ProposalHistoryEntry[]
}

export interface SpeakerIn {
  email?: string
  display_name?: string
  biography?: string
  use_gravatar?: boolean
}

export interface ProposalDetail {
  id: number
  title: string
  submission_type: string
  area?: string | null
  language?: string | null
  abstract: string
  description: string
  internal_notes: string
  occurrence_count: number
  duration_days: number
  duration_time_per_day: string
  is_basic_course: boolean
  max_participants: number
  material_cost_eur: string
  preferred_dates: string
  is_regular_member: boolean
  has_building_access: boolean
  owner?: UserBasic | null
  editors?: UserBasic[]
}

export async function fetchProposal(proposalId: string): Promise<ProposalDetail> {
  const { data, error, response } = await client.GET('/api/v1/proposals/{proposal_id}', {
    params: {
      path: {
        proposal_id: proposalId,
      },
    },
  })

  if (error || !response.ok || !data) {
    throw new Error(`Failed to fetch proposal: ${response.statusText}`)
  }

  return data as unknown as ProposalDetail
}

export async function updateProposal(proposalId: string, formData: {
  title?: string
  submission_type?: string
  area?: string | null
  language?: string | null
  abstract?: string
  description?: string
  internal_notes?: string
  occurrence_count?: number
  duration_days?: number
  duration_time_per_day?: string
  is_basic_course?: boolean
  max_participants?: number
  material_cost_eur?: string
  preferred_dates?: string
  is_regular_member?: boolean
  has_building_access?: boolean
  // owner_id removed - owner is set on creation and cannot be changed
  editor_ids?: string[]
}): Promise<ProposalDetail> {
  const { data, error, response } = await client.PUT('/api/v1/proposals/{proposal_id}', {
    params: {
      path: {
        proposal_id: proposalId,
      },
    },
    body: formData,
  })

  if (error || !response.ok || !data) {
    throw new Error(`Failed to update proposal: ${response.statusText}`)
  }

  return data as unknown as ProposalDetail
}

// Speaker Management API Functions

export interface SpeakerOut {
  id: number
  email: string
  display_name: string
  biography: string
  profile_picture?: string | null
  use_gravatar: boolean
}

export interface ProposalSpeakerOut {
  id: string
  speaker: SpeakerOut
  role: string
  sort_order: number
}

export async function addSpeakerToProposal(
  proposalId: string,
  speaker: SpeakerIn
): Promise<ProposalSpeakerOut> {
  const { data, error, response } = await client.POST('/api/v1/proposals/{proposal_id}/speakers', {
    params: {
      path: {
        proposal_id: proposalId,
      },
    },
    body: speaker,
  })

  if (error || !response.ok || !data) {
    throw new Error(`Failed to add speaker: ${response.statusText}`)
  }

  return data as unknown as ProposalSpeakerOut
}

export async function fetchProposalSpeakers(proposalId: string): Promise<ProposalSpeakerOut[]> {
  const { data, error, response } = await client.GET('/api/v1/proposals/{proposal_id}/speakers', {
    params: {
      path: {
        proposal_id: proposalId,
      },
    },
  })

  if (error || !response.ok || !data) {
    throw new Error(`Failed to fetch speakers: ${response.statusText}`)
  }

  return data as unknown as ProposalSpeakerOut[]
}

export async function updateSpeaker(
  proposalId: string,
  speakerId: string,
  speaker: SpeakerIn
): Promise<ProposalSpeakerOut> {
  const { data, error, response } = await client.PUT('/api/v1/proposals/{proposal_id}/speakers/{speaker_id}', {
    params: {
      path: {
        proposal_id: proposalId,
        speaker_id: speakerId,
      },
    },
    body: speaker,
  })

  if (error || !response.ok || !data) {
    throw new Error(`Failed to update speaker: ${response.statusText}`)
  }

  return data as unknown as ProposalSpeakerOut
}

export async function removeSpeaker(proposalId: string, speakerId: string): Promise<void> {
  const { error, response } = await client.DELETE('/api/v1/proposals/{proposal_id}/speakers/{speaker_id}', {
    params: {
      path: {
        proposal_id: proposalId,
        speaker_id: speakerId,
      },
    },
  })

  if (error || !response.ok) {
    throw new Error(`Failed to remove speaker: ${response.statusText}`)
  }
}

// Lookup table API Functions

export interface LookupItem {
  code: string
  label: string
  description?: string | null
  is_active?: boolean
  sort_order?: number
}

export async function fetchSubmissionTypes(): Promise<LookupItem[]> {
  const { data, error, response } = await client.GET('/api/v1/submission_types', {})

  if (error || !response.ok) {
    console.error('Failed to fetch submission types:', response?.statusText)
    return []
  }

  return (data as unknown as LookupItem[]) || []
}

export async function fetchProposalLanguages(): Promise<LookupItem[]> {
  const { data, error, response } = await client.GET('/api/v1/proposal_languages', {})

  if (error || !response.ok) {
    console.error('Failed to fetch proposal languages:', response?.statusText)
    return []
  }

  return (data as unknown as LookupItem[]) || []
}

export async function fetchProposalAreas(): Promise<LookupItem[]> {
  const { data, error, response } = await client.GET('/api/v1/proposal_areas', {})

  if (error || !response.ok) {
    console.error('Failed to fetch proposal areas:', response?.statusText)
    return []
  }

  return (data as unknown as LookupItem[]) || []
}

export interface ExternalCalendarEvent {
  id: string
  title: string
  startUtc: string
  endUtc: string
  source: string
}

export async function fetchExternalCalendarEvents(
  startUtc: string,
  endUtc: string
): Promise<ExternalCalendarEvent[]> {
  const { data, error, response } = await client.GET('/api/v1/calendar/events', {
    params: {
      query: {
        start_utc: startUtc,
        end_utc: endUtc,
      },
    },
  })

  if (error || !response.ok) {
    throw new Error(`Failed to fetch external calendar events: ${response.statusText}`)
  }

  return (data as unknown as ExternalCalendarEvent[]) || []
}

export interface ProposalEventSummary {
  id: string
  name: string
  startTime: string
  endTime: string
  series_id: string
  series_name: string
}

export async function fetchProposalEvents(proposalId: string): Promise<ProposalEventSummary[]> {
  const { data, error, response } = await client.GET('/api/v1/proposals/{proposal_id}/events', {
    params: {
      path: {
        proposal_id: proposalId,
      },
    },
  })

  if (error || !response.ok) {
    throw new Error(`Failed to fetch proposal events: ${response.statusText}`)
  }

  return (data as unknown as ProposalEventSummary[]) || []
}

