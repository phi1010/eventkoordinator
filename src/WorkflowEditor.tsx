import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  addEdge,
  reconnectEdge,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type Connection,
  type NodeProps,
  Handle,
  Position,
  MarkerType,
  ConnectionMode,
  ReactFlowProvider,
  useReactFlow,
  Panel,
  applyNodeChanges,
  applyEdgeChanges,
  type NodeChange,
  type EdgeChange,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { getCsrfToken } from './api'
import styles from './WorkflowEditor.module.css'

// ─── Types ───────────────────────────────────────────────────────────────────

interface WfStateData {
  label: string
  name: string
  isInitial: boolean
  usageCount?: number
  isRetiring?: boolean
  [key: string]: unknown
}

interface WfEdgeData {
  label: string
  [key: string]: unknown
}

// All nodes share Record<string,unknown> data so special nodes can coexist.
type AnyWfNode = Node<Record<string, unknown>>
type WfEdge = Edge<WfEdgeData>

// IDs for the singleton special nodes
const ID_FROM_ANY = '__from_any__'
const ID_FROM_UNDEFINED = '__from_undefined__'
const ID_KEEP_STATE = '__keep_state__'

function nodeStateData(n: AnyWfNode): WfStateData {
  return n.data as unknown as WfStateData
}

interface WorkflowStateOut {
  name: string
  label: Record<string, string>
  is_initial: boolean
  position_x: number
  position_y: number
}

interface WorkflowTransitionOut {
  name: string
  label: Record<string, string>
  from_state: string | null
  from_undefined_only: boolean
  to_state: string
  source_handle: string
  target_handle: string
}

interface WorkflowDefinitionOut {
  id: string
  name: string
  description: string
  initial_state: string | null
  states: WorkflowStateOut[]
  transitions: WorkflowTransitionOut[]
}

// ─── API helpers ──────────────────────────────────────────────────────────────

async function apiFetch(url: string, method: string, body?: unknown) {
  const token = await getCsrfToken()
  const res = await fetch(url, {
    method,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { 'X-CSRFToken': token } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  return res
}

async function listWorkflows(): Promise<WorkflowDefinitionOut[]> {
  const res = await apiFetch('/api/udm/workflows/', 'GET')
  if (!res.ok) throw new Error('Failed to load workflows')
  return res.json()
}

async function createWorkflow(payload: unknown): Promise<WorkflowDefinitionOut> {
  const res = await apiFetch('/api/udm/workflows/', 'POST', payload)
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(JSON.stringify(err))
  }
  return res.json()
}

async function updateWorkflow(id: string, payload: unknown): Promise<WorkflowDefinitionOut> {
  const res = await apiFetch(`/api/udm/workflows/${id}/`, 'PUT', payload)
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(JSON.stringify(err))
  }
  return res.json()
}

async function deleteWorkflow(id: string): Promise<void> {
  const res = await apiFetch(`/api/udm/workflows/${id}/`, 'DELETE')
  if (!res.ok && res.status !== 204) throw new Error('Failed to delete workflow')
}

async function fetchStateCounts(workflowId: string): Promise<Record<string, number>> {
  const res = await apiFetch(`/api/udm/workflows/${workflowId}/state-counts/`, 'GET')
  if (!res.ok) return {}
  return res.json()
}

// ─── Conversions ──────────────────────────────────────────────────────────────

const NODE_WIDTH = 240
const NODE_HEIGHT = 135

function wfToReactFlow(wf: WorkflowDefinitionOut): { nodes: AnyWfNode[]; edges: WfEdge[] } {
  const stateNodes: AnyWfNode[] = wf.states.map((s) => ({
    id: s.name,
    type: 'workflowState',
    position: { x: s.position_x, y: s.position_y },
    data: {
      label: s.label['en'] ?? Object.values(s.label)[0] ?? s.name,
      name: s.name,
      isInitial: s.is_initial,
    } as Record<string, unknown>,
  }))

  // Calculate bounding box to place special nodes sensibly
  const xs = stateNodes.map((n) => n.position.x)
  const ys = stateNodes.map((n) => n.position.y)
  const minX = xs.length ? Math.min(...xs) : 0
  const maxX = xs.length ? Math.max(...xs) : 400
  const midY = ys.length ? (Math.min(...ys) + Math.max(...ys)) / 2 : 100

  const nodes: AnyWfNode[] = [...stateNodes]
  const edges: WfEdge[] = []
  let hasFromAny = false
  let hasFromUndefined = false
  let hasKeepState = false

  for (const t of wf.transitions) {
    const edgeBase: Omit<WfEdge, 'id' | 'source' | 'target' | 'sourceHandle' | 'targetHandle'> = {
      data: { label: t.label['en'] ?? Object.values(t.label)[0] ?? t.name },
      label: t.label['en'] ?? Object.values(t.label)[0] ?? t.name,
      markerEnd: { type: MarkerType.ArrowClosed },
      type: 'smoothstep',
      reconnectable: true,
    }

    if (t.from_state === null && !t.from_undefined_only) {
      // From Any
      if (!hasFromAny) {
        nodes.push({ id: ID_FROM_ANY, type: 'fromAny', position: { x: minX - 200, y: midY - 40 }, data: {} })
        hasFromAny = true
      }
      edges.push({ ...edgeBase, id: t.name, source: ID_FROM_ANY, target: t.to_state, sourceHandle: t.source_handle || null, targetHandle: t.target_handle || null })
    } else if (t.from_state === null && t.from_undefined_only) {
      // From Undefined
      if (!hasFromUndefined) {
        nodes.push({ id: ID_FROM_UNDEFINED, type: 'fromUndefined', position: { x: minX - 200, y: midY + 40 }, data: {} })
        hasFromUndefined = true
      }
      edges.push({ ...edgeBase, id: t.name, source: ID_FROM_UNDEFINED, target: t.to_state, sourceHandle: t.source_handle || null, targetHandle: t.target_handle || null })
    } else if (t.from_state !== null && t.from_state === t.to_state) {
      // Keep State (self-loop)
      if (!hasKeepState) {
        nodes.push({ id: ID_KEEP_STATE, type: 'keepState', position: { x: maxX + NODE_WIDTH + 50, y: midY - 30 }, data: {} })
        hasKeepState = true
      }
      edges.push({ ...edgeBase, id: t.name, source: t.from_state, target: ID_KEEP_STATE, sourceHandle: t.source_handle || null, targetHandle: t.target_handle || null })
    } else {
      edges.push({ ...edgeBase, id: t.name, source: t.from_state ?? '', target: t.to_state, sourceHandle: t.source_handle || null, targetHandle: t.target_handle || null })
    }
  }

  return { nodes, edges }
}

function reactFlowToWf(
  nodes: AnyWfNode[],
  edges: WfEdge[],
  name: string,
  description: string,
) {
  const stateNodes = nodes.filter((n) => n.type === 'workflowState')
  const validStateIds = new Set(stateNodes.map((n) => n.id))

  // Migration edges are ephemeral editor instructions — not saved as transitions.
  const migrations = edges
    .filter((e) => e.data?.isMigration && validStateIds.has(e.source) && validStateIds.has(e.target))
    .map((e) => ({ from_state: e.source, to_state: e.target }))

  const transitions = edges
    .filter((e) => e.source && e.target && !e.data?.isMigration)
    .map((e) => {
      const srcType = nodes.find((n) => n.id === e.source)?.type
      const tgtType = nodes.find((n) => n.id === e.target)?.type

      let from_state: string | null = e.source
      let from_undefined_only = false
      let to_state = e.target

      if (srcType === 'fromAny') {
        from_state = null
        from_undefined_only = false
      } else if (srcType === 'fromUndefined') {
        from_state = null
        from_undefined_only = true
      }

      if (tgtType === 'keepState') {
        // Self-loop: to_state = from_state
        to_state = from_state ?? ''
      }

      // Skip edges that reference missing real states
      if (to_state === '' || !validStateIds.has(to_state)) return null
      if (from_state !== null && !validStateIds.has(from_state)) return null

      return {
        name: e.id,
        label: { en: String((e.data as WfEdgeData | undefined)?.label ?? e.id) },
        from_state,
        from_undefined_only,
        to_state,
        source_handle: e.sourceHandle ?? '',
        target_handle: e.targetHandle ?? '',
      }
    })
    .filter(Boolean)

  return {
    name,
    description,
    states: stateNodes.map((n) => {
      const d = nodeStateData(n)
      return {
        name: d.name,
        label: { en: d.label },
        is_initial: d.isInitial,
        position_x: n.position.x,
        position_y: n.position.y,
      }
    }),
    transitions,
    migrations,
  }
}

// ─── Proposal workflow example ────────────────────────────────────────────────

const mkEdge = (id: string, src: string, tgt: string, sh: string, th: string, lbl: string): WfEdge => ({
  id,
  source: src,
  target: tgt,
  sourceHandle: sh,
  targetHandle: th,
  data: { label: lbl },
  label: lbl,
  markerEnd: { type: MarkerType.ArrowClosed },
  type: 'smoothstep',
  reconnectable: true,
})

const PROPOSAL_EXAMPLE: { nodes: AnyWfNode[]; edges: WfEdge[] } = {
  nodes: [
    { id: 'draft',     type: 'workflowState', position: { x: 60,  y: 220 }, data: { label: 'Draft',     name: 'draft',     isInitial: true  } },
    { id: 'submitted', type: 'workflowState', position: { x: 380, y: 100 }, data: { label: 'Submitted', name: 'submitted', isInitial: false } },
    { id: 'revise',    type: 'workflowState', position: { x: 380, y: 340 }, data: { label: 'Revise',    name: 'revise',    isInitial: false } },
    { id: 'accepted',  type: 'workflowState', position: { x: 700, y: 20  }, data: { label: 'Accepted',  name: 'accepted',  isInitial: false } },
    { id: 'rejected',  type: 'workflowState', position: { x: 700, y: 220 }, data: { label: 'Rejected',  name: 'rejected',  isInitial: false } },
  ],
  edges: [
    mkEdge('submit',           'draft',     'submitted', 'right-top',    'left-top',     'Submit'),
    mkEdge('resubmit',         'revise',    'submitted', 'top-center',   'bottom-center','Resubmit'),
    mkEdge('request-revision', 'submitted', 'revise',    'bottom-center','top-center',   'Request Revision'),
    mkEdge('allow-revision',   'rejected',  'revise',    'bottom-left',  'right-bottom', 'Allow Revision'),
    mkEdge('accept',           'submitted', 'accepted',  'right-top',    'left-top',     'Accept'),
    mkEdge('reject',           'submitted', 'rejected',  'right-bottom', 'left-top',     'Reject'),
  ],
}

// ─── Custom 16:9 state node ───────────────────────────────────────────────────

function WorkflowStateNode({ data, selected }: NodeProps) {
  const d = data as WfStateData
  return (
    <div
      className={[styles.wfNode, selected ? styles.wfNodeSelected : '', d.isInitial ? styles.wfNodeInitial : ''].join(' ')}
      style={{ width: NODE_WIDTH, height: NODE_HEIGHT }}
    >
      <Handle type="source" position={Position.Top}    id="top-left"      style={{ left: '25%' }}  className={styles.handle} />
      <Handle type="source" position={Position.Top}    id="top-center"    style={{ left: '50%' }}  className={styles.handle} />
      <Handle type="source" position={Position.Top}    id="top-right"     style={{ left: '75%' }}  className={styles.handle} />
      <Handle type="source" position={Position.Bottom} id="bottom-left"   style={{ left: '25%' }}  className={styles.handle} />
      <Handle type="source" position={Position.Bottom} id="bottom-center" style={{ left: '50%' }}  className={styles.handle} />
      <Handle type="source" position={Position.Bottom} id="bottom-right"  style={{ left: '75%' }}  className={styles.handle} />
      <Handle type="source" position={Position.Left}   id="left-top"      style={{ top:  '33%' }}  className={styles.handle} />
      <Handle type="source" position={Position.Left}   id="left-bottom"   style={{ top:  '67%' }}  className={styles.handle} />
      <Handle type="source" position={Position.Right}  id="right-top"     style={{ top:  '33%' }}  className={styles.handle} />
      <Handle type="source" position={Position.Right}  id="right-bottom"  style={{ top:  '67%' }}  className={styles.handle} />
      <div className={styles.wfNodeContent}>
        {d.isInitial && <span className={styles.initialBadge}>●</span>}
        <span className={styles.wfNodeLabel}>{d.label}</span>
        <span className={styles.wfNodeSlug}>{d.name}</span>
      </div>
      {d.isRetiring && <span className={styles.retiringBadge}>RETIRING</span>}
      {d.usageCount !== undefined && (
        <span className={`${styles.countBadge} ${d.usageCount > 0 ? styles.countBadgeActive : styles.countBadgeMuted}`}>
          {d.usageCount}
        </span>
      )}
    </div>
  )
}

// ─── Special nodes (smaller, 4 handles one per side) ─────────────────────────

function SpecialNodeHandles({ type }: { type: 'source' | 'target' }) {
  return (
    <>
      <Handle type={type} position={Position.Top}    id="top"    className={styles.handle} />
      <Handle type={type} position={Position.Bottom} id="bottom" className={styles.handle} />
      <Handle type={type} position={Position.Left}   id="left"   className={styles.handle} />
      <Handle type={type} position={Position.Right}  id="right"  className={styles.handle} />
    </>
  )
}

function FromAnyNode({ selected }: NodeProps) {
  return (
    <div className={[styles.specialNode, styles.fromAnyNode, selected ? styles.wfNodeSelected : ''].join(' ')}>
      <SpecialNodeHandles type="source" />
      <span className={styles.specialNodeLabel}>From Any</span>
      <span className={styles.specialNodeSub}>any state → …</span>
    </div>
  )
}

function FromUndefinedNode({ selected }: NodeProps) {
  return (
    <div className={[styles.specialNode, styles.fromUndefinedNode, selected ? styles.wfNodeSelected : ''].join(' ')}>
      <SpecialNodeHandles type="source" />
      <span className={styles.specialNodeLabel}>From Undefined</span>
      <span className={styles.specialNodeSub}>null state → …</span>
    </div>
  )
}

function KeepStateNode({ selected }: NodeProps) {
  return (
    <div className={[styles.specialNode, styles.keepStateNode, selected ? styles.wfNodeSelected : ''].join(' ')}>
      <SpecialNodeHandles type="target" />
      <span className={styles.specialNodeLabel}>Keep State</span>
      <span className={styles.specialNodeSub}>… → same state</span>
    </div>
  )
}

const NODE_TYPES = {
  workflowState: WorkflowStateNode,
  fromAny: FromAnyNode,
  fromUndefined: FromUndefinedNode,
  keepState: KeepStateNode,
}

// ─── Slug helpers ─────────────────────────────────────────────────────────────

function toSlug(text: string, prefix: string): string {
  const base = text.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^[^a-z]+/, '').replace(/_+$/, '')
  return base.length > 0 ? base : `${prefix}_${Math.random().toString(36).slice(2, 7)}`
}

function uniqueSlug(base: string, existing: Set<string>): string {
  if (!existing.has(base)) return base
  let i = 2
  while (existing.has(`${base}_${i}`)) i++
  return `${base}_${i}`
}

// ─── Properties panel ─────────────────────────────────────────────────────────

interface PropsPanelProps {
  nodes: AnyWfNode[]
  edges: WfEdge[]
  selectedNodeIds: string[]
  selectedEdgeIds: string[]
  onNodeChange: (id: string, patch: Partial<WfStateData>) => void
  onEdgeChange: (id: string, patch: Partial<WfEdgeData>) => void
  onDeleteSelected: () => void
  orphanedStates: WorkflowStateOut[]
  stateCounts: Record<string, number>
  onReadd: (state: WorkflowStateOut) => void
}

const SPECIAL_DESCRIPTIONS: Record<string, string> = {
  [ID_FROM_ANY]:       'Transitions connecting here fire from any workflow state.',
  [ID_FROM_UNDEFINED]: 'Transitions connecting here fire only when the field has no state yet (null).',
  [ID_KEEP_STATE]:     'Transitions from a state to this node keep that state unchanged (self-loop).',
}

function PropertiesPanel({ nodes, edges, selectedNodeIds, selectedEdgeIds, onNodeChange, onEdgeChange, onDeleteSelected, orphanedStates, stateCounts, onReadd }: PropsPanelProps) {
  const selNodes = nodes.filter((n) => selectedNodeIds.includes(n.id))
  const selEdges = edges.filter((e) => selectedEdgeIds.includes(e.id) && !e.data?.isMigration)
  const selMigrationEdges = edges.filter((e) => selectedEdgeIds.includes(e.id) && e.data?.isMigration)
  const total = selNodes.length + selEdges.length + selMigrationEdges.length

  const orphanedSection = orphanedStates.length > 0 && (
    <div className={styles.orphanedSection}>
      <div className={styles.orphanedHeader}>⚠ Removed states with live data</div>
      <p className={styles.orphanedHint}>
        Saving will set these entities to no state. Re-add before saving to preserve them.
      </p>
      {orphanedStates.map(s => {
        const label = s.label['en'] ?? Object.values(s.label)[0] ?? s.name
        const count = stateCounts[s.name] ?? 0
        return (
          <div key={s.name} className={styles.orphanedItem}>
            <div className={styles.orphanedItemInfo}>
              <span className={styles.orphanedItemName}>{label}</span>
              <span className={styles.orphanedItemCount}>{count} entit{count === 1 ? 'y' : 'ies'}</span>
            </div>
            <button className={styles.readdBtn} onClick={() => onReadd(s)}>Re-add</button>
          </div>
        )
      })}
    </div>
  )

  if (total === 0) {
    return (
      <div className={styles.propsPanel}>
        {orphanedSection}
        <p className={styles.propsPanelHint}>Select a state or transition to edit its properties.</p>
      </div>
    )
  }

  return (
    <div className={styles.propsPanel}>
      {orphanedSection}
      <div className={styles.propsPanelHeader}>
        <span>{total} selected</span>
        <button className={styles.deleteBtn} onClick={onDeleteSelected} title="Delete selected">✕ Delete</button>
      </div>

      {selNodes.map((n) => {
        if (n.type !== 'workflowState') {
          return (
            <div key={n.id} className={styles.propsSection}>
              <div className={styles.propsSectionTitle}>
                {n.type === 'fromAny' ? 'From Any' : n.type === 'fromUndefined' ? 'From Undefined' : 'Keep State'}
              </div>
              <p className={styles.specialDesc}>{SPECIAL_DESCRIPTIONS[n.id] ?? ''}</p>
            </div>
          )
        }
        const d = nodeStateData(n)
        return (
          <div key={n.id} className={styles.propsSection}>
            <div className={styles.propsSectionTitle}>State: {n.id}</div>
            <label className={styles.propsLabel}>Display label
              <input className={styles.propsInput} value={d.label} onChange={(e) => onNodeChange(n.id, { label: e.target.value })} />
            </label>
            <label className={styles.propsLabel}>Internal name (slug)
              <input className={styles.propsInput} value={d.name} readOnly title="Slug is set at creation time" />
            </label>
            <label className={styles.propsCheckbox}>
              <input type="checkbox" checked={d.isInitial} onChange={(e) => onNodeChange(n.id, { isInitial: e.target.checked })} />
              Initial state
            </label>
          </div>
        )
      })}

      {selMigrationEdges.map((e) => (
        <div key={e.id} className={styles.propsSection}>
          <div className={styles.propsSectionTitle}>Migration: {e.source} → {e.target}</div>
          <p className={styles.specialDesc}>
            On save, all entities in state <strong>{e.source}</strong> will be moved to <strong>{e.target}</strong>, then <strong>{e.source}</strong> will be deleted.
          </p>
        </div>
      ))}

      {selEdges.map((e) => (
        <div key={e.id} className={styles.propsSection}>
          <div className={styles.propsSectionTitle}>Transition: {e.source} → {e.target}</div>
          <label className={styles.propsLabel}>Label
            <input
              className={styles.propsInput}
              value={String((e.data as WfEdgeData | undefined)?.label ?? '')}
              onChange={(ev) => onEdgeChange(e.id, { label: ev.target.value })}
            />
          </label>
          <label className={styles.propsLabel}>Internal name (slug)
            <input className={styles.propsInput} value={e.id} readOnly title="Slug is set at creation time" />
          </label>
        </div>
      ))}
    </div>
  )
}

// ─── Inner editor (needs ReactFlow context) ───────────────────────────────────

interface EditorInnerProps {
  initialNodes: AnyWfNode[]
  initialEdges: WfEdge[]
  workflowId: string | null
  workflowName: string
  workflowDescription: string
  onSaved: (wf: WorkflowDefinitionOut) => void
  initialStateCounts: Record<string, number>
  savedStates: WorkflowStateOut[]
}

function EditorInner({ initialNodes, initialEdges, workflowId, workflowName: initName, workflowDescription: initDesc, onSaved, initialStateCounts, savedStates }: EditorInnerProps) {
  const [nodes, setNodes] = useNodesState<AnyWfNode>(initialNodes)
  const [edges, setEdges] = useEdgesState<WfEdge>(initialEdges)
  const [name, setName] = useState(initName)
  const [desc, setDesc] = useState(initDesc)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saveSuccess, setSaveSuccess] = useState(false)
  const [migrationMode, setMigrationMode] = useState(false)
  const { fitView } = useReactFlow()

  useEffect(() => {
    setNodes(initialNodes)
    setEdges(initialEdges)
    setName(initName)
    setDesc(initDesc)
    setTimeout(() => fitView({ padding: 0.15 }), 50)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflowId, initName])

  // Inject usage counts into workflowState nodes whenever counts arrive/refresh
  useEffect(() => {
    if (Object.keys(initialStateCounts).length === 0) return
    setNodes(nds => nds.map(n =>
      n.type === 'workflowState'
        ? { ...n, data: { ...n.data, usageCount: initialStateCounts[n.id] ?? 0 } }
        : n,
    ))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialStateCounts])

  // Track which state nodes are sources of migration edges (retiring).
  // String key ensures the effect only fires when the actual set changes.
  const migrationSourcesKey = edges
    .filter((e) => e.data?.isMigration)
    .map((e) => e.source)
    .sort()
    .join(',')

  useEffect(() => {
    const retiringSrc = new Set(migrationSourcesKey.split(',').filter(Boolean))
    setNodes((nds) =>
      nds.map((n) =>
        n.type === 'workflowState'
          ? { ...n, data: { ...n.data, isRetiring: retiringSrc.has(n.id) } }
          : n,
      ),
    )
    setEdges((eds) =>
      eds.map((e) => {
        if (e.data?.isMigration) return e
        const dimmed = retiringSrc.has(e.target)
        return { ...e, style: { ...e.style, opacity: dimmed ? 0.35 : 1 } }
      }),
    )
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [migrationSourcesKey])

  const selectedNodeIds = nodes.filter((n) => n.selected).map((n) => n.id)
  const selectedEdgeIds = edges.filter((e) => e.selected).map((e) => e.id)

  const isValidConnection = useCallback(
    (connection: Connection) => {
      const src = nodes.find((n) => n.id === connection.source)
      const tgt = nodes.find((n) => n.id === connection.target)
      if (!src || !tgt) return false
      if (migrationMode) {
        // Migration edges only valid between regular state nodes
        return src.type === 'workflowState' && tgt.type === 'workflowState'
      }
      // fromAny / fromUndefined are source-only; reject any incoming edge
      if (tgt.type === 'fromAny' || tgt.type === 'fromUndefined') return false
      // keepState is target-only; reject any outgoing edge
      if (src.type === 'keepState') return false
      return true
    },
    [nodes, migrationMode],
  )

  const onConnect = useCallback(
    (connection: Connection) => {
      if (migrationMode) {
        // Create a migration edge; replace any existing migration edge from this source.
        const src = connection.source ?? ''
        setEdges((eds) => {
          const without = eds.filter((e) => !(e.data?.isMigration && e.source === src))
          const migEdge: WfEdge = {
            id: `migrate_${src}`,
            source: src,
            target: connection.target ?? '',
            sourceHandle: connection.sourceHandle ?? null,
            targetHandle: connection.targetHandle ?? null,
            type: 'smoothstep',
            data: { isMigration: true, label: '↦ migrate' },
            label: '↦ migrate',
            style: { stroke: '#f97316', strokeWidth: 3, strokeDasharray: '6 4' },
            markerEnd: { type: MarkerType.ArrowClosed, color: '#f97316' },
            reconnectable: true,
          }
          return [...without, migEdge]
        })
        return
      }
      const existingNames = new Set(edges.map((e) => e.id))
      const srcNode = nodes.find((n) => n.id === connection.source)
      // Special nodes don't have a meaningful label; fall back to a generic prefix
      const srcLabel = srcNode?.type === 'workflowState'
        ? String(nodeStateData(srcNode).label)
        : srcNode?.type === 'fromAny'   ? 'from_any'
        : srcNode?.type === 'fromUndefined' ? 'from_undef'
        : 't'
      const base = toSlug(srcLabel, 't')
      const slug = uniqueSlug(`t_${base}`, existingNames)
      setEdges((eds) =>
        addEdge({ ...connection, id: slug, data: { label: '' }, label: '', markerEnd: { type: MarkerType.ArrowClosed }, type: 'smoothstep', reconnectable: true }, eds),
      )
    },
    [edges, nodes, setEdges, migrationMode],
  )

  const onNodesChange = useCallback(
    (changes: NodeChange<AnyWfNode>[]) => setNodes((nds) => applyNodeChanges(changes, nds)),
    [setNodes],
  )

  const onEdgesChange = useCallback(
    (changes: EdgeChange<WfEdge>[]) => setEdges((eds) => applyEdgeChanges(changes, eds)),
    [setEdges],
  )

  const onReconnect = useCallback(
    (oldEdge: WfEdge, newConnection: Connection) =>
      setEdges((eds) => reconnectEdge(oldEdge, newConnection, eds)),
    [setEdges],
  )

  function addStateNode() {
    const existingNames = new Set(nodes.map((n) => n.id))
    const slug = uniqueSlug('state', existingNames)
    const hasInitial = nodes.some((n) => n.type === 'workflowState' && nodeStateData(n).isInitial)
    setNodes((nds) => [
      ...nds,
      {
        id: slug,
        type: 'workflowState',
        position: { x: 80 + nds.filter((n) => n.type === 'workflowState').length * 40, y: 80 },
        data: { label: 'New State', name: slug, isInitial: !hasInitial },
      },
    ])
  }

  function addSpecialNode(type: 'fromAny' | 'fromUndefined' | 'keepState') {
    const id = type === 'fromAny' ? ID_FROM_ANY : type === 'fromUndefined' ? ID_FROM_UNDEFINED : ID_KEEP_STATE
    if (nodes.some((n) => n.id === id)) return
    const xs = nodes.map((n) => n.position.x)
    const ys = nodes.map((n) => n.position.y)
    const midY = ys.length ? (Math.min(...ys) + Math.max(...ys)) / 2 : 100
    const x = type === 'keepState'
      ? (xs.length ? Math.max(...xs) + NODE_WIDTH + 60 : 600)
      : (xs.length ? Math.min(...xs) - 200 : -160)
    const y = type === 'fromUndefined' ? midY + 100 : midY - 30
    setNodes((nds) => [...nds, { id, type, position: { x, y }, data: {} }])
  }

  function handleNodeChange(id: string, patch: Partial<WfStateData>) {
    setNodes((nds) =>
      nds.map((n) => {
        if (n.id !== id || n.type !== 'workflowState') return n
        return { ...n, data: { ...n.data, ...patch } }
      }),
    )
    if (patch.isInitial) {
      setNodes((nds) =>
        nds.map((n) =>
          n.id !== id && n.type === 'workflowState' && (n.data as WfStateData).isInitial
            ? { ...n, data: { ...n.data, isInitial: false } }
            : n,
        ),
      )
    }
  }

  function handleEdgeChange(id: string, patch: Partial<WfEdgeData>) {
    setEdges((eds) =>
      eds.map((e) => {
        if (e.id !== id) return e
        const newData = { ...(e.data as WfEdgeData), ...patch }
        return { ...e, data: newData, label: newData.label }
      }),
    )
  }

  function deleteSelected() {
    setNodes((nds) => nds.filter((n) => !n.selected))
    setEdges((eds) => eds.filter((e) => !e.selected))
  }

  // Orphaned = saved states not currently on canvas but with live entity data
  const currentNodeIds = new Set(nodes.map((n) => n.id))
  const orphanedStates = savedStates.filter(
    (s) => !currentNodeIds.has(s.name) && (initialStateCounts[s.name] ?? 0) > 0,
  )

  function readd(state: WorkflowStateOut) {
    const label = state.label['en'] ?? Object.values(state.label)[0] ?? state.name
    const hasInitial = nodes.some((n) => n.type === 'workflowState' && nodeStateData(n).isInitial)
    setNodes((nds) => [
      ...nds,
      {
        id: state.name,
        type: 'workflowState',
        position: { x: state.position_x, y: state.position_y },
        data: {
          label,
          name: state.name,
          isInitial: state.is_initial && !hasInitial,
          usageCount: initialStateCounts[state.name] ?? 0,
        },
      },
    ])
  }

  async function handleSave() {
    // Pre-flight: states being deleted with live entities must have a migration edge.
    if (workflowId) {
      const migrationTargetMap = new Map(
        edges.filter((e) => e.data?.isMigration).map((e) => [e.source, e.target]),
      )
      const currentStateIds = new Set(
        nodes.filter((n) => n.type === 'workflowState').map((n) => n.id),
      )
      for (const s of savedStates) {
        if (currentStateIds.has(s.name)) continue
        const count = initialStateCounts[s.name] ?? 0
        if (count === 0) continue
        const migrateTarget = migrationTargetMap.get(s.name)
        if (!migrateTarget) {
          const label = s.label['en'] ?? Object.values(s.label)[0] ?? s.name
          setSaveError(
            `"${label}" has ${count} ${count === 1 ? 'entity' : 'entities'}. Draw a migration edge to move them, or re-add the state.`,
          )
          return
        }
        if (!currentStateIds.has(migrateTarget)) {
          const label = s.label['en'] ?? Object.values(s.label)[0] ?? s.name
          setSaveError(`Migration target for "${label}" is not on the canvas.`)
          return
        }
      }
    }

    setSaving(true)
    setSaveError(null)
    setSaveSuccess(false)
    try {
      const payload = reactFlowToWf(nodes, edges, name, desc)
      const result = workflowId
        ? await updateWorkflow(workflowId, payload)
        : await createWorkflow(payload)
      setSaveSuccess(true)
      onSaved(result)
      setTimeout(() => setSaveSuccess(false), 3000)
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const hasFromAny       = nodes.some((n) => n.id === ID_FROM_ANY)
  const hasFromUndefined = nodes.some((n) => n.id === ID_FROM_UNDEFINED)
  const hasKeepState     = nodes.some((n) => n.id === ID_KEEP_STATE)

  return (
    <div className={styles.editorRoot}>
      <div className={styles.toolbar}>
        <input className={styles.nameInput} placeholder="Workflow name" value={name} onChange={(e) => setName(e.target.value)} />
        <input className={styles.descInput} placeholder="Description (optional)" value={desc} onChange={(e) => setDesc(e.target.value)} />
        <span className={styles.toolbarSep} />
        <button className={styles.toolbarBtn} onClick={addStateNode}>+ State</button>
        <button className={`${styles.toolbarBtn} ${styles.fromAnyBtn}`}  onClick={() => addSpecialNode('fromAny')}  disabled={hasFromAny}  title="Add a 'From Any' virtual source node">+ From Any</button>
        <button className={`${styles.toolbarBtn} ${styles.fromUndefBtn}`} onClick={() => addSpecialNode('fromUndefined')} disabled={hasFromUndefined} title="Add a 'From Undefined' virtual source node">+ From Undefined</button>
        <button className={`${styles.toolbarBtn} ${styles.keepStateBtn}`} onClick={() => addSpecialNode('keepState')} disabled={hasKeepState} title="Add a 'Keep State' virtual target node">+ Keep State</button>
        <button
          className={`${styles.toolbarBtn} ${styles.migrateBtn} ${migrationMode ? styles.migrateBtnActive : ''}`}
          onClick={() => setMigrationMode((m) => !m)}
          title="Draw a migration edge to move entities from a retiring state to another on save"
        >
          ↦ Migrate{migrationMode ? ' (on)' : ''}
        </button>
        <span className={styles.toolbarSep} />
        <button className={`${styles.toolbarBtn} ${styles.saveBtn}`} onClick={handleSave} disabled={saving || !name.trim()}>
          {saving ? 'Saving…' : workflowId ? 'Save' : 'Save (create)'}
        </button>
        {saveSuccess && <span className={styles.saveOk}>✓ Saved</span>}
        {saveError   && <span className={styles.saveErr}>{saveError}</span>}
      </div>

      <div className={styles.canvasAndPanel}>
        <div className={styles.canvas}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onReconnect={onReconnect}
            isValidConnection={isValidConnection}
            nodeTypes={NODE_TYPES}
            connectionMode={ConnectionMode.Loose}
            defaultEdgeOptions={{ reconnectable: true }}
            fitView
            fitViewOptions={{ padding: 0.15 }}
            deleteKeyCode="Delete"
          >
            <Background />
            <Controls />
            <MiniMap />
            <Panel position="bottom-left">
              <span className={styles.hint}>Drag handles to connect • drag edge endpoints to reconnect • Delete removes selected</span>
            </Panel>
          </ReactFlow>
        </div>
        <PropertiesPanel
          nodes={nodes}
          edges={edges}
          selectedNodeIds={selectedNodeIds}
          selectedEdgeIds={selectedEdgeIds}
          onNodeChange={handleNodeChange}
          onEdgeChange={handleEdgeChange}
          onDeleteSelected={deleteSelected}
          orphanedStates={orphanedStates}
          stateCounts={initialStateCounts}
          onReadd={readd}
        />
      </div>
    </div>
  )
}

// ─── Outer shell with workflow list / load / examples ─────────────────────────

export function WorkflowEditor() {
  const [workflows, setWorkflows] = useState<WorkflowDefinitionOut[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [activeName, setActiveName] = useState('My Workflow')
  const [activeDesc, setActiveDesc] = useState('')
  const [activeNodes, setActiveNodes] = useState<AnyWfNode[]>([])
  const [activeEdges, setActiveEdges] = useState<WfEdge[]>([])
  const [activeStateCounts, setActiveStateCounts] = useState<Record<string, number>>({})
  const [activeSavedStates, setActiveSavedStates] = useState<WorkflowStateOut[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)
  const loadedRef = useRef(false)

  useEffect(() => {
    if (loadedRef.current) return
    loadedRef.current = true
    listWorkflows().then(setWorkflows).catch((e: Error) => setLoadError(e.message))
  }, [])

  function refreshCounts(id: string) {
    fetchStateCounts(id).then(setActiveStateCounts).catch(() => {})
  }

  function openNew() {
    setActiveId(null)
    setActiveName('New Workflow')
    setActiveDesc('')
    setActiveNodes([])
    setActiveEdges([])
    setActiveStateCounts({})
    setActiveSavedStates([])
  }

  function loadWorkflow(wf: WorkflowDefinitionOut) {
    const { nodes, edges } = wfToReactFlow(wf)
    setActiveId(wf.id)
    setActiveName(wf.name)
    setActiveDesc(wf.description)
    setActiveNodes(nodes)
    setActiveEdges(edges)
    setActiveSavedStates(wf.states)
    setActiveStateCounts({})
    refreshCounts(wf.id)
  }

  function loadExample() {
    setActiveId(null)
    setActiveName('Proposal Workflow')
    setActiveDesc('Workflow for conference talk proposals (from apiv1/flows.py)')
    setActiveNodes(PROPOSAL_EXAMPLE.nodes)
    setActiveEdges(PROPOSAL_EXAMPLE.edges)
    setActiveStateCounts({})
    setActiveSavedStates([])
  }

  async function handleDelete() {
    if (!activeId) return
    if (!confirm('Delete this workflow?')) return
    setDeleting(true)
    try {
      await deleteWorkflow(activeId)
      setWorkflows((wfs) => wfs.filter((w) => w.id !== activeId))
      openNew()
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Delete failed')
    } finally {
      setDeleting(false)
    }
  }

  function onSaved(wf: WorkflowDefinitionOut) {
    setActiveId(wf.id)
    setActiveName(wf.name)
    setActiveSavedStates(wf.states)
    setWorkflows((wfs) => {
      const idx = wfs.findIndex((w) => w.id === wf.id)
      return idx >= 0 ? wfs.map((w) => (w.id === wf.id ? wf : w)) : [...wfs, wf]
    })
    refreshCounts(wf.id)
  }

  return (
    <div className={styles.page}>
      <div className={styles.sidebar}>
        <div className={styles.sidebarHeader}>Workflows</div>
        {loadError && <div className={styles.loadError}>{loadError}</div>}
        <button className={styles.sidebarNewBtn} onClick={openNew}>+ New Workflow</button>
        <div className={styles.sidebarSection}>Examples</div>
        <button className={styles.sidebarItem} onClick={loadExample}>Proposal Workflow</button>
        <div className={styles.sidebarSection}>Saved</div>
        {workflows.length === 0 && <div className={styles.sidebarEmpty}>No saved workflows</div>}
        {workflows.map((wf) => (
          <button
            key={wf.id}
            className={`${styles.sidebarItem} ${wf.id === activeId ? styles.sidebarItemActive : ''}`}
            onClick={() => loadWorkflow(wf)}
          >
            {wf.name}
          </button>
        ))}
        {activeId && (
          <button className={styles.deleteWorkflowBtn} onClick={handleDelete} disabled={deleting}>
            {deleting ? 'Deleting…' : 'Delete workflow'}
          </button>
        )}
      </div>

      <div className={styles.editorArea}>
        <ReactFlowProvider>
          <EditorInner
            key={activeId ?? '__new__'}
            initialNodes={activeNodes}
            initialEdges={activeEdges}
            workflowId={activeId}
            workflowName={activeName}
            workflowDescription={activeDesc}
            onSaved={onSaved}
            initialStateCounts={activeStateCounts}
            savedStates={activeSavedStates}
          />
        </ReactFlowProvider>
      </div>
    </div>
  )
}
