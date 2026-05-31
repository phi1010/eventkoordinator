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
  allowsEdit: boolean
  [key: string]: unknown
}

interface WfEdgeData {
  label: string
  [key: string]: unknown
}

type WfNode = Node<WfStateData, 'workflowState'>
type WfEdge = Edge<WfEdgeData>

interface WorkflowStateOut {
  name: string
  label: Record<string, string>
  is_initial: boolean
  allows_edit: boolean
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

// ─── Conversions ──────────────────────────────────────────────────────────────

const NODE_WIDTH = 240
const NODE_HEIGHT = 135

function wfToReactFlow(wf: WorkflowDefinitionOut): { nodes: WfNode[]; edges: WfEdge[] } {
  const nodes: WfNode[] = wf.states.map((s) => ({
    id: s.name,
    type: 'workflowState' as const,
    position: { x: s.position_x, y: s.position_y },
    data: {
      label: s.label['en'] ?? Object.values(s.label)[0] ?? s.name,
      name: s.name,
      isInitial: s.is_initial,
      allowsEdit: s.allows_edit,
    },
  }))

  const edges: WfEdge[] = wf.transitions.map((t) => ({
    id: t.name,
    source: t.from_state ?? '',
    target: t.to_state,
    sourceHandle: t.source_handle || null,
    targetHandle: t.target_handle || null,
    data: { label: t.label['en'] ?? Object.values(t.label)[0] ?? t.name },
    label: t.label['en'] ?? Object.values(t.label)[0] ?? t.name,
    markerEnd: { type: MarkerType.ArrowClosed },
    type: 'smoothstep',
    reconnectable: true,
  }))

  return { nodes, edges }
}

function reactFlowToWf(
  nodes: WfNode[],
  edges: WfEdge[],
  name: string,
  description: string,
) {
  return {
    name,
    description,
    states: nodes.map((n) => ({
      name: n.data.name,
      label: { en: n.data.label },
      is_initial: n.data.isInitial,
      allows_edit: n.data.allowsEdit,
      position_x: n.position.x,
      position_y: n.position.y,
    })),
    transitions: edges
      .filter((e) => e.source && e.target)
      .map((e) => ({
        name: e.id,
        label: { en: String((e.data as WfEdgeData | undefined)?.label ?? e.id) },
        from_state: e.source || null,
        from_undefined_only: false,
        to_state: e.target,
        source_handle: e.sourceHandle ?? '',
        target_handle: e.targetHandle ?? '',
      })),
  }
}

// ─── Proposal workflow example ────────────────────────────────────────────────

const PROPOSAL_EXAMPLE: { nodes: WfNode[]; edges: WfEdge[] } = {
  nodes: [
    {
      id: 'draft',
      type: 'workflowState',
      position: { x: 60, y: 220 },
      data: { label: 'Draft', name: 'draft', isInitial: true, allowsEdit: true },
    },
    {
      id: 'submitted',
      type: 'workflowState',
      position: { x: 380, y: 100 },
      data: { label: 'Submitted', name: 'submitted', isInitial: false, allowsEdit: false },
    },
    {
      id: 'revise',
      type: 'workflowState',
      position: { x: 380, y: 340 },
      data: { label: 'Revise', name: 'revise', isInitial: false, allowsEdit: true },
    },
    {
      id: 'accepted',
      type: 'workflowState',
      position: { x: 700, y: 20 },
      data: { label: 'Accepted', name: 'accepted', isInitial: false, allowsEdit: false },
    },
    {
      id: 'rejected',
      type: 'workflowState',
      position: { x: 700, y: 220 },
      data: { label: 'Rejected', name: 'rejected', isInitial: false, allowsEdit: false },
    },
  ],
  edges: [
    {
      id: 'submit',
      source: 'draft',
      target: 'submitted',
      sourceHandle: 'right-top',
      targetHandle: 'left-top',
      data: { label: 'Submit' },
      label: 'Submit',
      markerEnd: { type: MarkerType.ArrowClosed },
      type: 'smoothstep',
      reconnectable: true,
    },
    {
      id: 'resubmit',
      source: 'revise',
      target: 'submitted',
      sourceHandle: 'top-center',
      targetHandle: 'bottom-center',
      data: { label: 'Resubmit' },
      label: 'Resubmit',
      markerEnd: { type: MarkerType.ArrowClosed },
      type: 'smoothstep',
    },
    {
      id: 'request-revision',
      source: 'submitted',
      target: 'revise',
      sourceHandle: 'bottom-center',
      targetHandle: 'top-center',
      data: { label: 'Request Revision' },
      label: 'Request Revision',
      markerEnd: { type: MarkerType.ArrowClosed },
      type: 'smoothstep',
    },
    {
      id: 'allow-revision',
      source: 'rejected',
      target: 'revise',
      sourceHandle: 'bottom-left',
      targetHandle: 'right-bottom',
      data: { label: 'Allow Revision' },
      label: 'Allow Revision',
      markerEnd: { type: MarkerType.ArrowClosed },
      type: 'smoothstep',
    },
    {
      id: 'accept',
      source: 'submitted',
      target: 'accepted',
      sourceHandle: 'right-top',
      targetHandle: 'left-top',
      data: { label: 'Accept' },
      label: 'Accept',
      markerEnd: { type: MarkerType.ArrowClosed },
      type: 'smoothstep',
    },
    {
      id: 'reject',
      source: 'submitted',
      target: 'rejected',
      sourceHandle: 'right-bottom',
      targetHandle: 'left-top',
      data: { label: 'Reject' },
      label: 'Reject',
      markerEnd: { type: MarkerType.ArrowClosed },
      type: 'smoothstep',
    },
  ],
}

// ─── Custom 16:9 node ─────────────────────────────────────────────────────────

function WorkflowStateNode({ data, selected }: NodeProps<WfNode>) {
  return (
    <div
      className={[styles.wfNode, selected ? styles.wfNodeSelected : '', data.isInitial ? styles.wfNodeInitial : ''].join(' ')}
      style={{ width: NODE_WIDTH, height: NODE_HEIGHT }}
    >
      {/* Top handles */}
      <Handle type="source" position={Position.Top} id="top-left"   style={{ left: '25%' }} className={styles.handle} />
      <Handle type="source" position={Position.Top} id="top-center" style={{ left: '50%' }} className={styles.handle} />
      <Handle type="source" position={Position.Top} id="top-right"  style={{ left: '75%' }} className={styles.handle} />
      {/* Bottom handles */}
      <Handle type="source" position={Position.Bottom} id="bottom-left"   style={{ left: '25%' }} className={styles.handle} />
      <Handle type="source" position={Position.Bottom} id="bottom-center" style={{ left: '50%' }} className={styles.handle} />
      <Handle type="source" position={Position.Bottom} id="bottom-right"  style={{ left: '75%' }} className={styles.handle} />
      {/* Left handles */}
      <Handle type="source" position={Position.Left} id="left-top"    style={{ top: '33%' }} className={styles.handle} />
      <Handle type="source" position={Position.Left} id="left-bottom" style={{ top: '67%' }} className={styles.handle} />
      {/* Right handles */}
      <Handle type="source" position={Position.Right} id="right-top"    style={{ top: '33%' }} className={styles.handle} />
      <Handle type="source" position={Position.Right} id="right-bottom" style={{ top: '67%' }} className={styles.handle} />

      <div className={styles.wfNodeContent}>
        {data.isInitial && <span className={styles.initialBadge}>●</span>}
        <span className={styles.wfNodeLabel}>{data.label}</span>
        <span className={styles.wfNodeSlug}>{data.name}</span>
      </div>
    </div>
  )
}

const NODE_TYPES = { workflowState: WorkflowStateNode }

// ─── slug helper ─────────────────────────────────────────────────────────────

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
  nodes: WfNode[]
  edges: WfEdge[]
  selectedNodeIds: string[]
  selectedEdgeIds: string[]
  onNodeChange: (id: string, patch: Partial<WfStateData>) => void
  onEdgeChange: (id: string, patch: Partial<WfEdgeData>) => void
  onDeleteSelected: () => void
}

function PropertiesPanel({
  nodes,
  edges,
  selectedNodeIds,
  selectedEdgeIds,
  onNodeChange,
  onEdgeChange,
  onDeleteSelected,
}: PropsPanelProps) {
  const selNodes = nodes.filter((n) => selectedNodeIds.includes(n.id))
  const selEdges = edges.filter((e) => selectedEdgeIds.includes(e.id))
  const total = selNodes.length + selEdges.length

  if (total === 0) {
    return (
      <div className={styles.propsPanel}>
        <p className={styles.propsPanelHint}>Select a state or transition to edit its properties.</p>
      </div>
    )
  }

  return (
    <div className={styles.propsPanel}>
      <div className={styles.propsPanelHeader}>
        <span>{total} selected</span>
        <button className={styles.deleteBtn} onClick={onDeleteSelected} title="Delete selected">✕ Delete</button>
      </div>

      {selNodes.map((n) => (
        <div key={n.id} className={styles.propsSection}>
          <div className={styles.propsSectionTitle}>State: {n.id}</div>
          <label className={styles.propsLabel}>Display label
            <input
              className={styles.propsInput}
              value={n.data.label}
              onChange={(e) => onNodeChange(n.id, { label: e.target.value })}
            />
          </label>
          <label className={styles.propsLabel}>Internal name (slug)
            <input
              className={styles.propsInput}
              value={n.data.name}
              readOnly
              title="Slug is set at creation time"
            />
          </label>
          <label className={styles.propsCheckbox}>
            <input
              type="checkbox"
              checked={n.data.isInitial}
              onChange={(e) => onNodeChange(n.id, { isInitial: e.target.checked })}
            />
            Initial state
          </label>
          <label className={styles.propsCheckbox}>
            <input
              type="checkbox"
              checked={n.data.allowsEdit}
              onChange={(e) => onNodeChange(n.id, { allowsEdit: e.target.checked })}
            />
            Allows editing
          </label>
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
            <input
              className={styles.propsInput}
              value={e.id}
              readOnly
              title="Slug is set at creation time"
            />
          </label>
        </div>
      ))}
    </div>
  )
}

// ─── Inner editor (needs ReactFlow context) ───────────────────────────────────

interface EditorInnerProps {
  initialNodes: WfNode[]
  initialEdges: WfEdge[]
  workflowId: string | null
  workflowName: string
  workflowDescription: string
  onSaved: (wf: WorkflowDefinitionOut) => void
}

function EditorInner({
  initialNodes,
  initialEdges,
  workflowId,
  workflowName: initName,
  workflowDescription: initDesc,
  onSaved,
}: EditorInnerProps) {
  const [nodes, setNodes] = useNodesState<WfNode>(initialNodes)
  const [edges, setEdges] = useEdgesState<WfEdge>(initialEdges)
  const [name, setName] = useState(initName)
  const [desc, setDesc] = useState(initDesc)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saveSuccess, setSaveSuccess] = useState(false)
  const { fitView } = useReactFlow()

  // reset when parent swaps workflow
  useEffect(() => {
    setNodes(initialNodes)
    setEdges(initialEdges)
    setName(initName)
    setDesc(initDesc)
    setTimeout(() => fitView({ padding: 0.15 }), 50)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflowId, initName])

  const selectedNodeIds = nodes.filter((n) => n.selected).map((n) => n.id)
  const selectedEdgeIds = edges.filter((e) => e.selected).map((e) => e.id)

  const onConnect = useCallback(
    (connection: Connection) => {
      const existingNames = new Set(edges.map((e) => e.id))
      const srcLabel = nodes.find((n) => n.id === connection.source)?.data.label ?? 'transition'
      const base = toSlug(srcLabel, 't')
      const slug = uniqueSlug(`t_${base}`, existingNames)
      setEdges((eds) =>
        addEdge(
          {
            ...connection,
            id: slug,
            data: { label: '' },
            label: '',
            markerEnd: { type: MarkerType.ArrowClosed },
            type: 'smoothstep',
          },
          eds,
        ),
      )
    },
    [edges, nodes, setEdges],
  )

  const onNodesChange = useCallback(
    (changes: NodeChange<WfNode>[]) => setNodes((nds) => applyNodeChanges(changes, nds)),
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

  function addNode() {
    const existingNames = new Set(nodes.map((n) => n.id))
    const slug = uniqueSlug('state', existingNames)
    const newNode: WfNode = {
      id: slug,
      type: 'workflowState',
      position: { x: 80 + nodes.length * 40, y: 80 + nodes.length * 40 },
      data: { label: 'New State', name: slug, isInitial: nodes.length === 0, allowsEdit: true },
    }
    setNodes((nds) => [...nds, newNode])
  }

  function handleNodeChange(id: string, patch: Partial<WfStateData>) {
    setNodes((nds) =>
      nds.map((n) => {
        if (n.id !== id) return n
        const updated = { ...n, data: { ...n.data, ...patch } }
        // Enforce single initial state
        if (patch.isInitial && patch.isInitial === true) {
          return updated
        }
        return updated
      }),
    )
    // Unset other initial nodes if this one was set as initial
    if (patch.isInitial) {
      setNodes((nds) =>
        nds.map((n) =>
          n.id !== id && n.data.isInitial ? { ...n, data: { ...n.data, isInitial: false } } : n,
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

  async function handleSave() {
    setSaving(true)
    setSaveError(null)
    setSaveSuccess(false)
    try {
      const payload = reactFlowToWf(nodes, edges, name, desc)
      const result = workflowId
        ? await updateWorkflow(workflowId, { ...payload, states: payload.states, transitions: payload.transitions })
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

  return (
    <div className={styles.editorRoot}>
      <div className={styles.toolbar}>
        <input
          className={styles.nameInput}
          placeholder="Workflow name"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <input
          className={styles.descInput}
          placeholder="Description (optional)"
          value={desc}
          onChange={(e) => setDesc(e.target.value)}
        />
        <button className={styles.toolbarBtn} onClick={addNode}>+ Add State</button>
        <button
          className={`${styles.toolbarBtn} ${styles.saveBtn}`}
          onClick={handleSave}
          disabled={saving || !name.trim()}
        >
          {saving ? 'Saving…' : workflowId ? 'Save' : 'Save (create)'}
        </button>
        {saveSuccess && <span className={styles.saveOk}>✓ Saved</span>}
        {saveError && <span className={styles.saveErr}>{saveError}</span>}
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
              <span className={styles.hint}>Drag handles to connect states • Delete key removes selected</span>
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
  const [activeNodes, setActiveNodes] = useState<WfNode[]>([])
  const [activeEdges, setActiveEdges] = useState<WfEdge[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)
  const loadedRef = useRef(false)

  useEffect(() => {
    if (loadedRef.current) return
    loadedRef.current = true
    listWorkflows()
      .then(setWorkflows)
      .catch((e) => setLoadError(e.message))
  }, [])

  function openNew() {
    setActiveId(null)
    setActiveName('New Workflow')
    setActiveDesc('')
    setActiveNodes([])
    setActiveEdges([])
  }

  function loadWorkflow(wf: WorkflowDefinitionOut) {
    const { nodes, edges } = wfToReactFlow(wf)
    setActiveId(wf.id)
    setActiveName(wf.name)
    setActiveDesc(wf.description)
    setActiveNodes(nodes)
    setActiveEdges(edges)
  }

  function loadExample() {
    setActiveId(null)
    setActiveName('Proposal Workflow')
    setActiveDesc('Workflow for conference talk proposals (from apiv1/flows.py)')
    setActiveNodes(PROPOSAL_EXAMPLE.nodes)
    setActiveEdges(PROPOSAL_EXAMPLE.edges)
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
    setWorkflows((wfs) => {
      const idx = wfs.findIndex((w) => w.id === wf.id)
      return idx >= 0 ? wfs.map((w) => (w.id === wf.id ? wf : w)) : [...wfs, wf]
    })
  }

  return (
    <div className={styles.page}>
      <div className={styles.sidebar}>
        <div className={styles.sidebarHeader}>Workflows</div>
        {loadError && <div className={styles.loadError}>{loadError}</div>}

        <button className={styles.sidebarNewBtn} onClick={openNew}>+ New Workflow</button>

        <div className={styles.sidebarSection}>Examples</div>
        <button
          className={styles.sidebarItem}
          onClick={loadExample}
        >
          Proposal Workflow
        </button>

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
          <button
            className={styles.deleteWorkflowBtn}
            onClick={handleDelete}
            disabled={deleting}
          >
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
          />
        </ReactFlowProvider>
      </div>
    </div>
  )
}
