import { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { getCurrentUser, searchUsers, fetchProposalAreas, type UserBasic, type LookupItem } from './api'
import styles from './ProposalReviews.module.css'

// ── Types ─────────────────────────────────────────────────────────────────────

type ReviewStatus = 'approved' | 'rejected' | 'revise' | 'pending' | 'note'

interface UserReview {
  id: string
  kind: 'user'
  reviewer: UserBasic & { system?: boolean }
  status: ReviewStatus
  comment: string
  requestedBy: string | null
  requestedAt: string | null
  completedAt: string | null
  requestedDirectly: boolean
  requestedViaGroups: string[]  // area codes
  previousStatus?: ReviewStatus
  previousComment?: string
  migrated?: boolean
}

interface GroupRequest {
  id: string
  kind: 'group'
  group: LookupItem
  requestedBy: string
  requestedAt: string
}

type ReviewEntry = UserReview | GroupRequest

// ── Helpers ───────────────────────────────────────────────────────────────────

const SYSTEM_USER: UserBasic & { system: true } = {
  id: 'u-system',
  username: 'System',
  system: true,
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0])
    .join('')
    .toUpperCase()
}

function fmtRel(iso: string | null | undefined): string {
  if (!iso) return ''
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

// Derive group status: worst-of for rejections/revisions, one-approver for approvals
function deriveGroupStatus(groupCode: string, allReviews: ReviewEntry[]): ReviewStatus {
  const memberReviews = allReviews.filter(
    (r): r is UserReview =>
      r.kind === 'user' && (r.requestedViaGroups || []).includes(groupCode),
  )
  if (memberReviews.some((r) => r.status === 'rejected')) return 'rejected'
  if (memberReviews.some((r) => r.status === 'revise')) return 'revise'
  if (memberReviews.some((r) => r.status === 'approved')) return 'approved'
  return 'pending'
}

function worstMemberVote(groupCode: string, allReviews: ReviewEntry[]): ReviewStatus | null {
  const RANK: Record<string, number> = { rejected: 3, revise: 2, approved: 1 }
  const decided = allReviews.filter(
    (r): r is UserReview =>
      r.kind === 'user' &&
      (r.requestedViaGroups || []).includes(groupCode) &&
      r.status !== 'pending',
  )
  if (decided.length === 0) return null
  return decided.reduce<ReviewStatus | null>(
    (w, r) => (!w ? r.status : (RANK[r.status] || 0) > (RANK[w] || 0) ? r.status : w),
    null,
  )
}

function statusCardClass(status: ReviewStatus): string {
  return {
    approved: styles.reviewCardApproved,
    rejected: styles.reviewCardRejected,
    revise: styles.reviewCardRevise,
    pending: styles.reviewCardPending,
    note: styles.reviewCardNote,
  }[status]
}

function statusBadgeClass(status: ReviewStatus): string {
  return {
    approved: styles.badgeApproved,
    rejected: styles.badgeRejected,
    revise: styles.badgeRevise,
    pending: styles.badgePending,
    note: styles.badgeNote,
  }[status]
}

function statusLabel(status: ReviewStatus): string {
  return {
    approved: 'Approved',
    rejected: 'Rejected',
    revise: 'Revisions requested',
    pending: 'Awaiting review',
    note: 'Comment',
  }[status]
}

// ── StatusBadge ───────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: ReviewStatus }) {
  return (
    <span className={`${styles.statusBadge} ${statusBadgeClass(status)}`}>
      <span className={styles.badgeDot} />
      {statusLabel(status)}
    </span>
  )
}

// ── UserPicker ────────────────────────────────────────────────────────────────

type PickResult =
  | { kind: 'user'; user: UserBasic }
  | { kind: 'group'; group: LookupItem }

interface UserPickerProps {
  excludeIds: string[]
  groups: LookupItem[]
  onPick: (result: PickResult) => void
}

function UserPicker({ excludeIds, groups, onPick }: UserPickerProps) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const [userResults, setUserResults] = useState<UserBasic[]>([])
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [])

  useEffect(() => {
    let cancelled = false
    searchUsers(q).then((results) => {
      if (!cancelled) setUserResults(results)
    })
    return () => { cancelled = true }
  }, [q])

  const filteredGroups = useMemo(
    () =>
      groups.filter(
        (g) => !q.trim() || g.label.toLowerCase().includes(q.toLowerCase()),
      ),
    [q, groups],
  )

  return (
    <div className={styles.userPickerWrap} ref={ref}>
      <input
        className={styles.userPickerInput}
        placeholder="Search a person or area to request review…"
        value={q}
        onFocus={() => setOpen(true)}
        onChange={(e) => { setQ(e.target.value); setOpen(true) }}
      />
      {open && (filteredGroups.length > 0 || userResults.length > 0) && (
        <div className={styles.userPickerMenu} role="listbox">
          {filteredGroups.length > 0 && (
            <div className={styles.pickerSectionLabel}>Areas / Workshops</div>
          )}
          {filteredGroups.map((g) => {
            const disabled = excludeIds.includes(g.code)
            return (
              <div
                key={g.code}
                className={`${styles.userPickerItem} ${styles.userPickerItemGroup} ${disabled ? styles.userPickerItemDisabled : ''}`}
                onClick={() => {
                  if (disabled) return
                  onPick({ kind: 'group', group: g })
                  setQ('')
                  setOpen(false)
                }}
              >
                <span className={`${styles.avatar} ${styles.avatarGroup}`}>{initials(g.label)}</span>
                <span>{g.label}</span>
                <span className={styles.userPickerItemRole}>
                  {disabled ? 'already added' : 'area'}
                </span>
              </div>
            )
          })}

          {userResults.length > 0 && (
            <div className={styles.pickerSectionLabel}>People</div>
          )}
          {userResults.map((u) => {
            const disabled = excludeIds.includes(u.id)
            return (
              <div
                key={u.id}
                className={`${styles.userPickerItem} ${disabled ? styles.userPickerItemDisabled : ''}`}
                onClick={() => {
                  if (disabled) return
                  onPick({ kind: 'user', user: u })
                  setQ('')
                  setOpen(false)
                }}
              >
                <span className={styles.avatar}>{initials(u.username)}</span>
                <span>{u.username}</span>
                {disabled && (
                  <span className={styles.userPickerItemRole}>already added</span>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ── ReviewCard ────────────────────────────────────────────────────────────────

interface ReviewCardProps {
  review: UserReview
  currentUserId: string
  onWithdraw: () => void
  onEditOwn: () => void
}

function ReviewCard({ review, currentUserId, onWithdraw, onEditOwn }: ReviewCardProps) {
  const isSelf = review.reviewer.id === currentUserId
  const isSystem = review.reviewer.system === true

  const cardClasses = [
    styles.reviewCard,
    statusCardClass(review.status),
    isSelf ? styles.reviewCardSelf : '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <div className={cardClasses}>
      <div className={styles.reviewHead}>
        <span className={styles.reviewer}>
          <span className={`${styles.avatar} ${isSystem ? styles.avatarSystem : ''}`}>
            {isSystem ? '⚙' : initials(review.reviewer.username)}
          </span>
          <span>{isSystem ? 'System' : review.reviewer.username}</span>
          {isSelf && <span className={styles.selfTag}>you</span>}
          {isSystem ? (
            <span className={styles.tagSoft} title="Migrated from the legacy moderation comment — original author unknown">
              migrated · author unknown
            </span>
          ) : null}
        </span>
        <StatusBadge status={review.status} />
        <span className={styles.reviewMeta}>
          {review.status === 'pending' ? (
            <span>requested {fmtRel(review.requestedAt)}</span>
          ) : (
            <span>{fmtRel(review.completedAt)}</span>
          )}
          {isSelf && review.status !== 'pending' && !isSystem && (
            <button className={styles.btnSubtle} onClick={onEditOwn}>edit</button>
          )}
          {review.status === 'pending' && !isSystem && (
            <button className={styles.iconBtn} title="Withdraw request" onClick={onWithdraw} aria-label="Withdraw request">
              ×
            </button>
          )}
        </span>
      </div>

      {review.status !== 'pending' ? (
        <div className={styles.reviewBody}>
          {review.comment || <em style={{ color: '#9ca3af' }}>No comment provided.</em>}
        </div>
      ) : (
        <div className={`${styles.reviewBody} ${styles.reviewBodyMuted}`}>
          Waiting for {review.reviewer.username.split(' ')[0]} to respond…
          {review.previousStatus && (
            <div style={{ marginTop: '0.5rem', fontStyle: 'normal', color: '#6b7280', fontSize: '0.85rem' }}>
              Previously voted <StatusBadge status={review.previousStatus} />
              {review.previousComment && (
                <div className={styles.prevVoteBlock}>"{review.previousComment}"</div>
              )}
            </div>
          )}
        </div>
      )}

      <div className={styles.reviewFootline}>
        {review.requestedDirectly && review.requestedBy && (
          <span className={styles.requestedBy}>
            requested directly by <strong>{review.requestedBy}</strong>
          </span>
        )}
        {(review.requestedViaGroups || []).map((code) => (
          <span key={code} className={`${styles.requestedBy} ${styles.viaGroup}`}>
            via <strong>{code}</strong>
          </span>
        ))}
        {isSystem && (
          <span className={styles.requestedBy}>
            migrated from <strong>moderation comment</strong>
          </span>
        )}
      </div>
    </div>
  )
}

// ── GroupReviewCard ───────────────────────────────────────────────────────────

interface GroupReviewCardProps {
  groupRequest: GroupRequest
  allReviews: ReviewEntry[]
  currentUserId: string
  groups: LookupItem[]
  onWithdraw: () => void
}

function GroupReviewCard({
  groupRequest,
  allReviews,
  currentUserId,
  onWithdraw,
}: GroupReviewCardProps) {
  const derived = deriveGroupStatus(groupRequest.group.code, allReviews)
  const worst = worstMemberVote(groupRequest.group.code, allReviews)

  const memberVotes = allReviews.filter(
    (r): r is UserReview =>
      r.kind === 'user' && (r.requestedViaGroups || []).includes(groupRequest.group.code),
  )

  const groupCardClass = [
    styles.reviewCard,
    styles.reviewCardGroup,
    {
      approved: styles.reviewCardGroupApproved,
      rejected: styles.reviewCardGroupRejected,
      revise: styles.reviewCardGroupRevise,
      pending: styles.reviewCardGroupPending,
      note: '',
    }[derived],
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <div className={groupCardClass}>
      <div className={styles.reviewHead}>
        <span className={styles.reviewer}>
          <span className={`${styles.avatar} ${styles.avatarGroup}`}>
            {initials(groupRequest.group.label)}
          </span>
          <span>{groupRequest.group.label}</span>
          <span className={styles.tagSoft}>area · workshop</span>
        </span>
        <StatusBadge status={derived} />
        <span className={styles.reviewMeta}>
          <span>requested {fmtRel(groupRequest.requestedAt)}</span>
          {derived !== 'approved' && (
            <button
              className={styles.iconBtn}
              title="Withdraw group request"
              onClick={onWithdraw}
              aria-label="Withdraw group request"
            >
              ×
            </button>
          )}
        </span>
      </div>

      <div className={styles.groupSummary}>
        <span><strong>{memberVotes.filter((r) => r.status !== 'pending').length}/{memberVotes.length}</strong> members voted</span>
        {derived === 'pending' && worst && (
          <span className={styles.groupTrending}>
            trending <StatusBadge status={worst} />
          </span>
        )}
        {derived === 'approved' && (
          <span style={{ color: '#2e7d32', fontWeight: 600 }}>
            ✓ one approval is enough — no rejections or revisions
          </span>
        )}
      </div>

      {memberVotes.length > 0 && (
        <div className={styles.memberChips}>
          {memberVotes.map((r) => {
            const isMe = r.reviewer.id === currentUserId
            const chipClass = [
              styles.memberChip,
              isMe ? styles.memberChipMe : '',
              r.status === 'approved' ? styles.memberChipApproved : '',
              r.status === 'rejected' ? styles.memberChipRejected : '',
              r.status === 'revise' ? styles.memberChipRevise : '',
            ]
              .filter(Boolean)
              .join(' ')
            return (
              <span
                key={r.reviewer.id}
                className={chipClass}
                title={r.comment ? `${r.reviewer.username}: ${r.comment}` : `${r.reviewer.username} — ${r.status}`}
              >
                <span className={`${styles.avatar} ${styles.avatarSmall}`}>
                  {initials(r.reviewer.username)}
                </span>
                <span>{r.reviewer.username.split(' ')[0]}</span>
                {isMe && <span className={styles.selfTag}>you</span>}
                <StatusBadge status={r.status} />
              </span>
            )
          })}
        </div>
      )}

      <div className={styles.reviewFootline}>
        {groupRequest.requestedBy && (
          <span className={styles.requestedBy}>
            requested by <strong>{groupRequest.requestedBy}</strong>
          </span>
        )}
        <span className={styles.fieldHint}>
          Any one member of this area can approve. Their comment lives in their own review card below.
        </span>
      </div>
    </div>
  )
}

// ── SelfReviewComposer ────────────────────────────────────────────────────────

interface SelfReviewComposerProps {
  currentUser: UserBasic
  existing: UserReview | undefined
  onSubmit: (vote: { status: ReviewStatus; comment: string }) => void
  onCancel?: () => void
}

function SelfReviewComposer({ currentUser, existing, onSubmit, onCancel }: SelfReviewComposerProps) {
  const isRequested = existing && existing.status === 'pending'
  const isEditing = existing && existing.status !== 'pending'
  const seedComment = existing?.comment || existing?.previousComment || ''
  const [comment, setComment] = useState(seedComment)
  const [open, setOpen] = useState(Boolean(existing))

  // Sync seed when existing changes (e.g. on edit click)
  useEffect(() => {
    setComment(existing?.comment || existing?.previousComment || '')
    setOpen(Boolean(existing))
  }, [existing?.id])

  if (!existing && !open) {
    return (
      <div className={styles.selfReviewForm}>
        <div className={styles.selfReviewHeader}>
          <span className={styles.reviewer}>
            <span className={styles.avatar}>{initials(currentUser.username)}</span>
            <span>{currentUser.username}</span>
            <span className={styles.selfTag}>you</span>
          </span>
          <span style={{ marginLeft: 'auto', color: '#6b7280', fontSize: '0.85rem' }}>
            You haven't been asked, but you can add your own review.
          </span>
        </div>
        <div className={styles.selfReviewRow}>
          <button className={`${styles.btn} ${styles.btnPrimary}`} onClick={() => setOpen(true)}>
            + Add my review
          </button>
        </div>
      </div>
    )
  }

  const submit = (status: ReviewStatus) => {
    onSubmit({ status, comment: comment.trim() })
    setComment('')
    setOpen(false)
  }

  const headerLabel = isRequested ? "You've been asked to review" : isEditing ? 'Editing your review' : 'New review'

  const formClasses = [
    styles.selfReviewForm,
    styles.selfReviewFormEditing,
    isRequested ? styles.selfReviewFormRequested : '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <div className={formClasses}>
      <div className={styles.selfReviewHeader}>
        <span className={styles.reviewer}>
          <span className={styles.avatar}>{initials(currentUser.username)}</span>
          <span>{currentUser.username}</span>
          <span className={styles.selfTag}>you</span>
        </span>
        <span className={styles.tagSoft}>{headerLabel}</span>
        {isRequested && existing.requestedBy && (
          <span style={{ marginLeft: 'auto', color: '#6b7280', fontSize: '0.82rem' }}>
            requested by <strong>{existing.requestedBy}</strong> {fmtRel(existing.requestedAt)}
          </span>
        )}
      </div>

      {isRequested && existing.previousStatus && (
        <div style={{ fontSize: '0.85rem', color: '#6b7280' }}>
          Resubmitted since your last vote. You previously voted <StatusBadge status={existing.previousStatus} />.
          {existing.previousComment && (
            <div className={styles.prevVoteBlock}>"{existing.previousComment}"</div>
          )}
        </div>
      )}

      <textarea
        className={styles.textarea}
        placeholder={
          isRequested
            ? 'Leave a comment explaining your decision…'
            : 'Share what you think. What works, what concerns you, what should change?'
        }
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        maxLength={2000}
        rows={4}
      />
      <div className={styles.selfReviewRow} style={{ justifyContent: 'space-between' }}>
        <div className={styles.selfReviewRow}>
          <button
            className={`${styles.btn} ${styles.btnApprove}`}
            onClick={() => submit('approved')}
            disabled={!comment.trim()}
          >
            ✓ Approve
          </button>
          <button
            className={`${styles.btn} ${styles.btnRevise}`}
            onClick={() => submit('revise')}
            disabled={!comment.trim()}
          >
            ↻ Request revisions
          </button>
          <button
            className={`${styles.btn} ${styles.btnReject}`}
            onClick={() => submit('rejected')}
            disabled={!comment.trim()}
          >
            ✕ Reject
          </button>
        </div>
        <button
          className={`${styles.btn} ${styles.btnGhost}`}
          onClick={() => {
            setOpen(false)
            setComment(existing?.comment || '')
            onCancel?.()
          }}
          style={{ visibility: isRequested ? 'hidden' : 'visible' }}
        >
          Cancel
        </button>
      </div>
      <span className={styles.fieldHint}>A comment is required so the author understands your decision.</span>
    </div>
  )
}

// ── ReviewsSection ────────────────────────────────────────────────────────────

interface ReviewsSectionProps {
  proposalId: string
  proposalStatus: string
  moderationComment?: string
  moderationCommentAt?: string
  canModerate: boolean
}

export function ReviewsSection({
  proposalId,
  proposalStatus,
  moderationComment,
  moderationCommentAt,
  canModerate,
}: ReviewsSectionProps) {
  const { t } = useTranslation()
  const [currentUser, setCurrentUser] = useState<UserBasic | null>(null)
  const [groups, setGroups] = useState<LookupItem[]>([])
  const [reviews, setReviews] = useState<ReviewEntry[]>([])
  const [editingOwn, setEditingOwn] = useState(false)
  const [pendingRequestee, setPendingRequestee] = useState<PickResult | null>(null)
  const prevStatusRef = useRef(proposalStatus)

  // Load current user and groups once
  useEffect(() => {
    getCurrentUser().then((u) => setCurrentUser({ id: u.user_id, username: u.username }))
    fetchProposalAreas().then(setGroups)
  }, [])

  // Seed legacy moderation comment as a System review when present
  useEffect(() => {
    if (!moderationComment) return
    setReviews((rs) => {
      if (rs.some((r) => r.kind === 'user' && r.reviewer.system)) return rs
      const legacyReview: UserReview = {
        id: 'rv-legacy-migration',
        kind: 'user',
        reviewer: SYSTEM_USER,
        status: 'note',
        comment: moderationComment,
        requestedBy: null,
        requestedAt: moderationCommentAt || null,
        completedAt: moderationCommentAt || null,
        requestedDirectly: false,
        requestedViaGroups: [],
        migrated: true,
      }
      return [legacyReview, ...rs]
    })
  }, [moderationComment, moderationCommentAt])

  // Reset reviews to pending on resubmission
  useEffect(() => {
    const prev = prevStatusRef.current
    prevStatusRef.current = proposalStatus
    if (
      proposalStatus === 'submitted' &&
      (prev === 'revise' || prev === 'rejected' || prev === 'draft')
    ) {
      setReviews((rs) =>
        rs.map((r) => {
          if (r.kind === 'user' && (r.status === 'note' || r.reviewer.system)) return r
          if (r.kind === 'group') return { ...r, requestedAt: new Date().toISOString() }
          if (r.status === 'pending') return r
          return {
            ...r,
            status: 'pending' as const,
            comment: '',
            completedAt: null,
            requestedAt: new Date().toISOString(),
            previousStatus: r.status,
            previousComment: r.comment,
          }
        }),
      )
    }
  }, [proposalStatus])

  const currentUserId = currentUser?.id ?? ''
  const currentUsername = currentUser?.username ?? ''

  // Ids already in the list (for picker exclusion)
  const excludeIds = reviews.map((r) =>
    r.kind === 'group' ? r.group.code : r.reviewer.id,
  )

  // Stats: count each direct ask once; group requests count once via derived status
  const stats = useMemo(() => {
    let approved = 0, revise = 0, rejected = 0, pending = 0
    for (const r of reviews) {
      if (r.kind === 'user' && r.status === 'note') continue
      // Skip user reviews that are solely group-request members (not direct asks)
      if (
        r.kind === 'user' &&
        !r.requestedDirectly &&
        (r.requestedViaGroups || []).length > 0
      ) continue

      const s = r.kind === 'group' ? deriveGroupStatus(r.group.code, reviews) : r.status
      if (s === 'approved') approved++
      else if (s === 'revise') revise++
      else if (s === 'rejected') rejected++
      else if (s === 'pending') pending++
    }
    return { approved, revise, rejected, pending, total: approved + revise + rejected + pending }
  }, [reviews])

  // Request a review from user or group
  const requestReview = useCallback(() => {
    if (!pendingRequestee || !currentUser) return
    const requestedBy = currentUser.username
    const now = new Date().toISOString()

    if (pendingRequestee.kind === 'group') {
      const g = pendingRequestee.group
      const groupReq: GroupRequest = {
        id: `rv-g-${g.code}-${Date.now()}`,
        kind: 'group',
        group: g,
        requestedBy,
        requestedAt: now,
      }
      setReviews((rs) => [...rs, groupReq])
    } else {
      const u = pendingRequestee.user
      setReviews((rs) => {
        const existing = rs.find((r): r is UserReview => r.kind === 'user' && r.reviewer.id === u.id)
        if (existing) {
          return rs.map((r) =>
            r.kind === 'user' && r.reviewer.id === u.id
              ? { ...r, requestedDirectly: true }
              : r,
          )
        }
        const newReview: UserReview = {
          id: `rv-${u.id}-${Date.now()}`,
          kind: 'user',
          reviewer: u,
          status: 'pending',
          comment: '',
          requestedBy,
          requestedAt: now,
          completedAt: null,
          requestedDirectly: true,
          requestedViaGroups: [],
        }
        return [...rs, newReview]
      })
    }
    setPendingRequestee(null)
  }, [pendingRequestee, currentUser])

  const withdrawReview = useCallback((id: string) => {
    setReviews((rs) => rs.filter((r) => r.id !== id))
  }, [])

  const submitOwnReview = useCallback(
    ({ status, comment }: { status: ReviewStatus; comment: string }) => {
      if (!currentUser) return
      setReviews((rs) => {
        const idx = rs.findIndex(
          (r): r is UserReview => r.kind === 'user' && r.reviewer.id === currentUser.id,
        )
        const updated: UserReview = {
          id: idx >= 0 ? (rs[idx] as UserReview).id : `rv-self-${Date.now()}`,
          kind: 'user',
          reviewer: currentUser,
          status,
          comment,
          requestedBy: idx >= 0 ? (rs[idx] as UserReview).requestedBy : null,
          requestedAt: idx >= 0 ? (rs[idx] as UserReview).requestedAt : new Date().toISOString(),
          completedAt: new Date().toISOString(),
          requestedDirectly: idx >= 0 ? (rs[idx] as UserReview).requestedDirectly : false,
          requestedViaGroups: idx >= 0 ? (rs[idx] as UserReview).requestedViaGroups : [],
        }
        if (idx >= 0) {
          const next = [...rs]
          next[idx] = updated
          return next
        }
        return [...rs, updated]
      })
      setEditingOwn(false)
    },
    [currentUser],
  )

  const ownReview = reviews.find(
    (r): r is UserReview => r.kind === 'user' && r.reviewer.id === currentUserId,
  )

  const isLocked = proposalStatus === 'accepted' || proposalStatus === 'archived'

  // Render order: note reviews first, then groups and users sorted by requestedAt
  const sortedReviews = useMemo(() => {
    const notes = reviews.filter((r): r is UserReview => r.kind === 'user' && r.status === 'note')
    const rest = reviews.filter((r) => !(r.kind === 'user' && r.status === 'note'))
    return [...notes, ...rest]
  }, [reviews])

  const isOwnPendingUser = (r: ReviewEntry): boolean =>
    r.kind === 'user' && r.reviewer.id === currentUserId && r.status === 'pending'

  if (!currentUser) return null

  return (
    <fieldset className={styles.reviewsFieldset}>
      <legend className={styles.reviewsLegend}>Reviews</legend>

      <div className={styles.reviewsHeader}>
        <div className={styles.reviewsCount}>
          {stats.total === 0 ? (
            <span>no reviews yet</span>
          ) : (
            <>
              {stats.approved > 0 && <span style={{ color: '#2e7d32' }}>{stats.approved} approved</span>}
              {stats.revise > 0 && <span style={{ color: '#8b6508' }}>{stats.revise} revise</span>}
              {stats.rejected > 0 && <span style={{ color: '#b71c1c' }}>{stats.rejected} rejected</span>}
              {stats.pending > 0 && <span style={{ color: '#b25e09' }}>{stats.pending} pending</span>}
            </>
          )}
        </div>
      </div>

      {stats.total > 0 && (
        <div className={styles.reviewsProgress}>
          <div className={styles.progressBar} aria-label="Review progress">
            {stats.approved > 0 && (
              <div
                className={`${styles.progressSeg} ${styles.progressSegApproved}`}
                style={{ width: `${(stats.approved / stats.total) * 100}%` }}
              />
            )}
            {stats.revise > 0 && (
              <div
                className={`${styles.progressSeg} ${styles.progressSegRevise}`}
                style={{ width: `${(stats.revise / stats.total) * 100}%` }}
              />
            )}
            {stats.rejected > 0 && (
              <div
                className={`${styles.progressSeg} ${styles.progressSegRejected}`}
                style={{ width: `${(stats.rejected / stats.total) * 100}%` }}
              />
            )}
          </div>
        </div>
      )}

      <div className={styles.reviewList}>
        {reviews.length === 0 && (
          <div className={`${styles.reviewBody} ${styles.reviewBodyMuted}`} style={{ padding: '0.5rem 0' }}>
            No reviews yet. Request one below or add your own.
          </div>
        )}

        {sortedReviews.map((r) => {
          if (isOwnPendingUser(r)) return null
          if (editingOwn && r.kind === 'user' && r.reviewer.id === currentUserId) return null
          if (r.kind === 'group') {
            return (
              <GroupReviewCard
                key={r.id}
                groupRequest={r}
                allReviews={reviews}
                currentUserId={currentUserId}
                groups={groups}
                onWithdraw={() => withdrawReview(r.id)}
              />
            )
          }
          return (
            <ReviewCard
              key={r.id}
              review={r}
              currentUserId={currentUserId}
              onWithdraw={() => withdrawReview(r.id)}
              onEditOwn={() => setEditingOwn(true)}
            />
          )
        })}
      </div>

      {!isLocked && (!ownReview || ownReview.status === 'pending' || editingOwn) && (
        <SelfReviewComposer
          currentUser={currentUser}
          existing={editingOwn ? ownReview : ownReview?.status === 'pending' ? ownReview : undefined}
          onSubmit={submitOwnReview}
          onCancel={() => setEditingOwn(false)}
        />
      )}

      {!isLocked && canModerate && (
        <div className={styles.requestRow}>
          <div className={styles.requestRowInner}>
            <UserPicker
              excludeIds={excludeIds}
              groups={groups}
              onPick={setPendingRequestee}
            />
            {pendingRequestee && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '0.85rem', color: '#374151' }}>
                  Request review from:{' '}
                  <strong>
                    {pendingRequestee.kind === 'group'
                      ? pendingRequestee.group.label
                      : pendingRequestee.user.username}
                  </strong>
                </span>
                <button className={`${styles.btn} ${styles.btnPrimary}`} onClick={requestReview}>
                  + Request review
                </button>
                <button className={`${styles.btn} ${styles.btnGhost}`} onClick={() => setPendingRequestee(null)}>
                  Cancel
                </button>
              </div>
            )}
            <span className={styles.requestHint}>
              Pick a person or an area. Area reviews ask all members to comment.
            </span>
          </div>
        </div>
      )}
    </fieldset>
  )
}

// ── Review gating helper (exported for ProposalTransitionButtons) ──────────────

export function computeReviewGating(reviews: ReviewEntry[]): {
  canAccept: boolean
  hint: string | null
} {
  const effectiveStatuses: ReviewStatus[] = []

  for (const r of reviews) {
    if (r.kind === 'user' && r.status === 'note') continue
    if (
      r.kind === 'user' &&
      !r.requestedDirectly &&
      (r.requestedViaGroups || []).length > 0
    ) continue
    effectiveStatuses.push(r.kind === 'group' ? deriveGroupStatus(r.group.code, reviews) : r.status)
  }

  const pending = effectiveStatuses.filter((s) => s === 'pending').length
  const rejected = effectiveStatuses.filter((s) => s === 'rejected').length
  const revise = effectiveStatuses.filter((s) => s === 'revise').length

  if (effectiveStatuses.length === 0) return { canAccept: true, hint: null }
  if (rejected > 0)
    return {
      canAccept: false,
      hint: `${rejected} reviewer${rejected > 1 ? 's' : ''} rejected this proposal.`,
    }
  if (revise > 0)
    return {
      canAccept: false,
      hint: `${revise} reviewer${revise > 1 ? 's' : ''} requested changes.`,
    }
  if (pending > 0)
    return {
      canAccept: false,
      hint: `Waiting on ${pending} pending review${pending > 1 ? 's' : ''}.`,
    }
  return { canAccept: true, hint: 'All reviews approved — ready to accept.' }
}
