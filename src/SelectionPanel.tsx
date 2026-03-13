import { useState, useEffect, useRef, useCallback } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import {
  searchProposals,
  createProposal,
  deleteProposal,
  checkObjectPermission,
  fetchProposalTransitions,
} from './api'
import { usePermissions } from './usePermissions'
import { ProposalEditor } from './ProposalEditor'
import styles from './SelectionPanel.module.css'

export interface SelectionItem {
  id: string
  [key: string]: unknown
}

export interface SelectionPanelProps<T extends SelectionItem> {
  items: T[]
  selectedItemId: string
  onSelectionChange: (itemId: string) => void
  onBeforeSelectionChange?: (newItemId: string) => Promise<boolean>
  renderItemLabel: (item: T) => React.ReactNode
  renderContent: (selectedItem: T) => React.ReactNode
  sidebarTitle: string
  belowTitleElement?: React.ReactElement
  isNested?: boolean
}

export function SelectionPanel<T extends SelectionItem>({
  items,
  selectedItemId,
  onSelectionChange,
  onBeforeSelectionChange,
  renderItemLabel,
  renderContent,
  sidebarTitle,
  belowTitleElement,
  isNested = false,
}: SelectionPanelProps<T>) {
  const [comboboxOpen, setComboboxOpen] = useState(false)
  const selectedItem = items.find((item) => item.id === selectedItemId)
  const itemListRef = useRef<HTMLUListElement>(null)
  const activeItemRef = useRef<HTMLLIElement>(null)
  const listboxId = `combobox-list-${sidebarTitle.replace(/\s+/g, '-').toLowerCase()}`

  // Scroll to active item when selection changes
  useEffect(() => {
    if (activeItemRef.current && itemListRef.current) {
      // Use setTimeout to ensure the DOM has updated
      setTimeout(() => {
        activeItemRef.current?.scrollIntoView({
          behavior: 'smooth',
          block: 'nearest',
        })
      }, 100)
    }
  }, [selectedItemId])

  const handleSelectionChange = async (itemId: string) => {
    if (itemId === selectedItemId) {
      return
    }

    if (onBeforeSelectionChange) {
      const confirmed = await onBeforeSelectionChange(itemId)
      if (!confirmed) {
        return
      }
    }

    onSelectionChange(itemId)
  }

  if (!selectedItem) return null

  const containerClass = isNested ? styles.nestedContainer : styles.selectorContainer
  const sidebarClass = isNested ? styles.nestedSidebar : styles.sidebar
  const comboboxWrapperClass = isNested ? styles.nestedComboboxWrapper : styles.comboboxWrapper

  return (
    <div className={containerClass}>
      {/* Sidebar - visible on wide screens */}
      <aside className={sidebarClass} aria-label={sidebarTitle}>
        <h2>{sidebarTitle}</h2>
        {belowTitleElement && (
          <div className={styles.belowTitleElement}>
            {belowTitleElement}
          </div>
        )}
        <ul className={styles.itemList} role="listbox" aria-label={sidebarTitle} ref={itemListRef}>
          {items.map((item) => (
            <li
              key={item.id}
              ref={selectedItem.id === item.id ? activeItemRef : null}
              className={`${styles.item} ${selectedItem.id === item.id ? styles.active : ''}`}
              onClick={() => void handleSelectionChange(item.id)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  void handleSelectionChange(item.id)
                }
              }}
              tabIndex={0}
              role="option"
              aria-selected={selectedItem.id === item.id}
            >
              {renderItemLabel(item)}
            </li>
          ))}
        </ul>
      </aside>

      {/* Combobox - visible on narrow screens */}
      <div className={comboboxWrapperClass}>
        <div className={styles.comboboxContainer}>
          <button
            className={styles.comboboxButton}
            onClick={() => setComboboxOpen(!comboboxOpen)}
            aria-expanded={comboboxOpen}
            aria-haspopup="listbox"
            aria-controls={listboxId}
            aria-label={`Select ${sidebarTitle}`}
          >
            <span className={styles.comboboxValue}>{renderItemLabel(selectedItem)}</span>
            <span className={styles.comboboxIcon} aria-hidden="true">▼</span>
          </button>

          {comboboxOpen && (
            <ul className={styles.comboboxList} role="listbox" id={listboxId} aria-label={sidebarTitle}>
              {items.map((item) => (
                <li
                  key={item.id}
                  className={`${styles.comboboxItem} ${selectedItem.id === item.id ? styles.active : ''}`}
                  onClick={() => {
                    void handleSelectionChange(item.id)
                    setComboboxOpen(false)
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      void handleSelectionChange(item.id)
                      setComboboxOpen(false)
                    }
                  }}
                  role="option"
                  aria-selected={selectedItem.id === item.id}
                  tabIndex={0}
                >
                  {renderItemLabel(item)}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Main content area */}
      <main className={styles.content} aria-label={`${sidebarTitle} content`}>
        {renderContent(selectedItem)}
      </main>
    </div>
  )
}



export interface ProposalItem extends SelectionItem {
  id: string
  proposalId: string
  title: string
  submission_type: string
  workflow_status?: string
}

interface ProposalSelectionPanelProps {
  onCreateProposal?: () => void
  onProposalSave?: (formData: unknown) => void
}

export function ProposalSelectionPanel({ onCreateProposal, onProposalSave }: ProposalSelectionPanelProps) {
  const [proposals, setProposals] = useState<ProposalItem[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedProposalId, setSelectedProposalId] = useState<string>('')
  const [isCreating, setIsCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [canViewSelectedProposal, setCanViewSelectedProposal] = useState<boolean | null>(null)
  const [canEditSelectedProposal, setCanEditSelectedProposal] = useState<boolean | null>(null)
  const [canDeleteSelectedProposal, setCanDeleteSelectedProposal] = useState(false)
  const [editorPermissionLoading, setEditorPermissionLoading] = useState(false)
  const { canAdd, canBrowse } = usePermissions()
  const navigate = useNavigate()
  const { proposalId: urlProposalId } = useParams<{ proposalId?: string }>()

  const formatWorkflowStatus = (status?: string) => {
    if (!status) return 'unknown'
    return status.replace(/_/g, ' ')
  }

  const refreshWorkflowStatuses = useCallback(async (proposalItems: ProposalItem[]) => {
    const realItems = proposalItems.filter((p) => p.proposalId !== '')
    if (realItems.length === 0) {
      return
    }

    const statusEntries = await Promise.all(
      realItems.map(async (item) => {
        try {
          const transitions = await fetchProposalTransitions(item.proposalId)
          return [item.id, transitions.current_status] as const
        } catch (statusError) {
          console.warn(`Failed to load workflow status for proposal ${item.proposalId}:`, statusError)
          return [item.id, item.workflow_status || 'unknown'] as const
        }
      })
    )

    const statusById = new Map(statusEntries)
    setProposals((prev) => prev.map((item) => {
      if (!statusById.has(item.id)) {
        return item
      }
      return {
        ...item,
        workflow_status: statusById.get(item.id) || 'unknown',
      }
    }))
  }, [])

  // Load proposals helper (used on mount and after saves)
  const loadProposals = useCallback(async () => {
    try {
      setLoading(true)
      const results = await searchProposals('')
      const items: ProposalItem[] = results.map((p) => ({
        id: String(p.id),
        proposalId: p.id,
        title: p.title,
        submission_type: p.submission_type,
        workflow_status: 'unknown',
      }))

      if (items.length === 0) {
        const emptyItem: ProposalItem = {
          id: 'empty',
          proposalId: '',
          title: 'No proposals yet',
          submission_type: 'Click "Create New Proposal" to get started',
        }
        setProposals([emptyItem])
        setSelectedProposalId('empty')
      } else {
        setProposals(items)
        void refreshWorkflowStatuses(items)
        // Determine effective selection from URL, falling back to first proposal
        const effectiveProposalId = (urlProposalId && items.some((p) => p.id === urlProposalId))
          ? urlProposalId
          : items[0].id
        setSelectedProposalId(effectiveProposalId)
      }
    } catch (error) {
      console.error('Failed to load proposals:', error)
    } finally {
      setLoading(false)
    }
  }, [refreshWorkflowStatuses, urlProposalId])

  useEffect(() => {
    void loadProposals()
  }, [loadProposals])

  useEffect(() => {
    const checkSelectedProposalPermissions = async () => {
      const selected = proposals.find((item) => item.id === selectedProposalId)
      if (!selected || !selected.proposalId) {
        setCanViewSelectedProposal(true)
        setCanEditSelectedProposal(true)
        setCanDeleteSelectedProposal(false)
        return
      }

      setEditorPermissionLoading(true)
      try {
        const [canView, canChange, canDelete] = await Promise.all([
          checkObjectPermission({
            app: 'apiv1',
            action: 'view',
            object_type: 'proposal',
            object_id: selected.proposalId,
          }),
          checkObjectPermission({
            app: 'apiv1',
            action: 'change',
            object_type: 'proposal',
            object_id: selected.proposalId,
          }),
          checkObjectPermission({
            app: 'apiv1',
            action: 'delete',
            object_type: 'proposal',
            object_id: selected.proposalId,
          }),
        ])
        setCanViewSelectedProposal(canView)
        setCanEditSelectedProposal(canChange)
        setCanDeleteSelectedProposal(canDelete)
      } finally {
        setEditorPermissionLoading(false)
      }
    }

    void checkSelectedProposalPermissions()
  }, [proposals, selectedProposalId])

  const handleCreateProposal = async () => {
    try {
      setIsCreating(true)
      setCreateError(null)

      const newProposal = await createProposal()

      // Add new proposal to the list
      const newItem: ProposalItem = {
        id: String(newProposal.id),
        proposalId: String(newProposal.id),
        title: newProposal.title,
        submission_type: newProposal.submission_type,
        workflow_status: 'draft',
      }

      setProposals((prev) => [newItem, ...prev])
      setSelectedProposalId(newItem.id)
      navigate(`/proposal-editor/${newItem.id}`)

      if (onCreateProposal) {
        onCreateProposal()
      }
    } catch (error) {
      setCreateError(error instanceof Error ? error.message : 'Failed to create proposal')
      console.error('Failed to create proposal:', error)
    } finally {
      setIsCreating(false)
    }
  }

  const handleProposalChange = (newProposalId: string) => {
    navigate(`/proposal-editor/${newProposalId}`)
  }

  const handleProposalDelete = async (proposalId: string) => {
    await deleteProposal(proposalId)

    const remainingProposals = proposals.filter((proposal) => proposal.proposalId !== proposalId)

    if (remainingProposals.length === 0) {
      const emptyItem: ProposalItem = {
        id: 'empty',
        proposalId: '',
        title: 'No proposals yet',
        submission_type: 'Click "Create New Proposal" to get started',
      }
      setProposals([emptyItem])
      setSelectedProposalId('empty')
      navigate('/proposal-editor')
      return
    }

    const nextProposalId = remainingProposals[0].id
    setProposals(remainingProposals)
    setSelectedProposalId(nextProposalId)
    navigate(`/proposal-editor/${nextProposalId}`)
  }

  if (loading) {
    return <div style={{ padding: '2rem', textAlign: 'center' }}>Loading proposals...</div>
  }

  if (!canBrowse('proposal')) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center', color: '#666' }}>
        <p style={{ fontSize: '1.2rem', marginBottom: '1rem' }}>Access Denied</p>
        <p>You don't have permission to browse proposals</p>
      </div>
    )
  }

  // Determine effective selection from URL, falling back to first proposal
  const effectiveProposalId = (urlProposalId && proposals.some((p) => p.id === urlProposalId))
    ? urlProposalId
    : proposals[0]?.id ?? ''

  // If the URL proposalId is absent or invalid and we have proposals, redirect to the first one
  if (proposals.length > 0 && effectiveProposalId !== urlProposalId) {
    return <Navigate to={`/proposal-editor/${effectiveProposalId}`} replace />
  }

  const createButton = canAdd('proposal') ? (
    <div style={{ marginBottom: '1rem' }}>
      <button
        type="button"
        onClick={handleCreateProposal}
        disabled={isCreating}
        style={{
          width: '100%',
          padding: '0.75rem',
          marginBottom: createError ? '0.5rem' : 0,
          backgroundColor: '#4caf50',
          color: 'white',
          border: 'none',
          borderRadius: '4px',
          cursor: isCreating ? 'not-allowed' : 'pointer',
          fontWeight: 600,
          opacity: isCreating ? 0.7 : 1,
        }}
      >
        {isCreating ? 'Creating...' : 'Create New Proposal'}
      </button>
      {createError && (
        <div className={styles.inlineError}>
          {createError}
        </div>
      )}
    </div>
  ) : undefined

  const renderProposalLabel = (proposal: ProposalItem) => (
    <div className={styles.proposalLabel}>
      <div className={styles.proposalLabelHeader}>
        <span className={styles.proposalTitle}>{proposal.title}</span>
        {proposal.proposalId !== '' && (
          <span className={styles.workflowBadge} aria-hidden="true">
            {formatWorkflowStatus(proposal.workflow_status)}
          </span>
        )}
      </div>
      <div className={styles.proposalSubmissionType}>{proposal.submission_type}</div>
    </div>
  )

  return (
    <SelectionPanel<ProposalItem>
      items={proposals}
      selectedItemId={effectiveProposalId}
      onSelectionChange={handleProposalChange}
      renderItemLabel={renderProposalLabel}
      renderContent={(proposal) => (
        proposal.proposalId === '' ? (
          <div style={{ padding: '2rem', textAlign: 'center', color: '#666' }}>
            <p style={{ fontSize: '1.2rem', marginBottom: '1rem' }}>No proposals yet</p>
            <p>Click the "Create New Proposal" button to get started</p>
          </div>
        ) : editorPermissionLoading ? (
          <div style={{ padding: '2rem', textAlign: 'center', color: '#666' }}>
            Checking proposal permissions...
          </div>
        ) : !canViewSelectedProposal ? (
          <div style={{ padding: '2rem', textAlign: 'center', color: '#666' }}>
            <p style={{ fontSize: '1.2rem', marginBottom: '1rem' }}>Access Denied</p>
            <p>You don't have permission to view this proposal</p>
          </div>
        ) : (
          <ProposalEditor
            key={proposal.proposalId}
            proposalId={proposal.proposalId}
            canEdit={canEditSelectedProposal ?? false}
            canDelete={canDeleteSelectedProposal}
            onDeleteProposal={handleProposalDelete}
            onProposalSave={async (formData) => {
              // Refresh proposal list after a proposal is saved
              try {
                await loadProposals()
              } catch (err) {
                console.error('Failed to refresh proposals after save:', err)
              }
              // Forward event to parent if provided
              if (onProposalSave) {
                try {
                  onProposalSave(formData)
                } catch (err) {
                  console.error('Parent onProposalSave errored:', err)
                }
              }
            }}
          />
        )
      )}
      sidebarTitle="Proposals"
      belowTitleElement={createButton}
    />
  )
}
