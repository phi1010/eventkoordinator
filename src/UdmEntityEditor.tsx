import { useState, useEffect, useCallback, useRef, useId, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { StacksEditor, EditorType } from '@stackoverflow/stacks-editor'
import '@stackoverflow/stacks-editor/dist/styles.css'
import './stacks-scoped.css'
import {
  udmGetEntity,
  udmGetConfigVersion,
  udmValidateEntity,
  udmPatchEntity,
  udmTransitionEntity,
  udmEntityHistory,
  udmSearchUsers,
  udmSearchGroups,
  udmSearchEntities,
  udmUploadStagingFile,
  UdmApiError,
  type EntityOut,
  type ConfigVersionOut,
  type FieldDefinitionOut,
  type WorkflowTransitionOut,
  type WorkflowDefinitionOut,
  type EditHistoryOut,
  type UserAutocompleteItem,
  type GroupAutocompleteItem,
  type EntityAutocompleteItem,
  type PolicyMessage,
} from './apiUdm'
import { MigrationAssistant } from './UdmMigration'
import styles from './UdmEntityEditor.module.css'

// ── Helpers ───────────────────────────────────────────────────────────────────

function getLang(map: Record<string, string>, uiLang: string): string {
  return map[uiLang] ?? map['en'] ?? Object.values(map)[0] ?? ''
}

function getFieldValue(entity: EntityOut, slug: string, lang = ''): unknown {
  const fv = entity.field_values.find(v => v.field_slug === slug && v.language === lang)
  return fv?.value ?? null
}

function getAllLangValues(entity: EntityOut, slug: string): Record<string, unknown> {
  const result: Record<string, unknown> = {}
  entity.field_values
    .filter(v => v.field_slug === slug)
    .forEach(v => { result[v.language] = v.value })
  return result
}

// ── Severity helpers ──────────────────────────────────────────────────────────

const SEVERITY_ORDER = ['info', 'warning', 'error', 'critical']

function maxSeverity(msgs: PolicyMessage[]): string | undefined {
  let max: string | undefined
  for (const m of msgs) {
    if (!max || SEVERITY_ORDER.indexOf(m.level) > SEVERITY_ORDER.indexOf(max)) max = m.level
  }
  return max
}

/** Border color for a field card. Edited (orange) beats warning/info but not error/critical. */
function highlightBorderColor(severity: string | undefined, isDirty: boolean): string | undefined {
  if (!severity) return undefined
  if (severity === 'critical' || severity === 'error') return '#dc2626'
  if (isDirty) return '#f9a825'
  if (severity === 'warning') return '#eab308'
  return '#3b82f6'
}

/** Outline/label color for a single sub-field inside a submodel card. */
function subFieldColor(severity: string | undefined): string {
  if (severity === 'critical' || severity === 'error') return '#dc2626'
  if (severity === 'warning') return '#d97706'
  if (severity === 'info') return '#2563eb'
  return '#444'
}

// ── Autocomplete hook ─────────────────────────────────────────────────────────

function useAutocomplete<T>(
  fetcher: (q: string) => Promise<T[]>,
  delay = 300,
) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<T[]>([])
  const [open, setOpen] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const search = useCallback((q: string) => {
    setQuery(q)
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(async () => {
      if (q.length < 1) { setResults([]); setOpen(false); return }
      const res = await fetcher(q)
      setResults(res)
      setOpen(true)
    }, delay)
  }, [fetcher, delay])

  return { query, setQuery, results, setResults, open, setOpen, search }
}

// ── Field renderers ───────────────────────────────────────────────────────────

interface FieldInputProps {
  fd: FieldDefinitionOut
  value: unknown
  onChange: (v: unknown) => void
  disabled: boolean
  lang?: string
  entityChildren?: Record<string, unknown[]>
  subFieldSeverities?: Record<string, string>
  subFieldMessages?: Record<string, PolicyMessage[]>
}

// ── Submodel editor ───────────────────────────────────────────────────────────

// Shape of a serialized child node (from entity.children[slug])
interface ChildNode {
  id: string
  field_values: Array<{ field_slug: string; data_type: string; value: unknown; language: string }>
  children: Record<string, unknown[]>
  current_state: string | null
}

interface SubmodelOp {
  op: 'create' | 'update' | 'delete'
  id?: string
  fields?: Record<string, unknown>
  sort_order?: number
}

// Local representation of one child (existing or pending-create)
interface LocalChild {
  key: string           // stable React key: existing id or "_new_N"
  id: string | null     // null for not-yet-saved new items
  dirty: Record<string, unknown>
  saved: ChildNode | null
  deleted: boolean
}

function buildOps(items: LocalChild[]): SubmodelOp[] {
  const ops: SubmodelOp[] = []
  for (const item of items) {
    if (item.deleted && item.id) {
      ops.push({ op: 'delete', id: item.id })
    } else if (!item.id && !item.deleted) {
      ops.push({ op: 'create', fields: item.dirty })
    } else if (item.id && !item.deleted && Object.keys(item.dirty).length > 0) {
      ops.push({ op: 'update', id: item.id, fields: item.dirty })
    }
  }
  return ops
}

function getChildFieldValue(child: LocalChild, slug: string, lang = ''): unknown {
  if (slug in child.dirty) {
    const d = child.dirty[slug]
    if (lang && typeof d === 'object' && d !== null) return (d as Record<string, unknown>)[lang]
    return d
  }
  const fv = child.saved?.field_values.find(v => v.field_slug === slug && v.language === lang)
  return fv?.value ?? null
}

function buildPreviewLabel(
  subFields: FieldDefinitionOut[],
  fieldValues: Array<{ field_slug: string; language: string; value: unknown }>,
  dirty: Record<string, unknown>,
  uiLang: string,
  fallback: string,
): string {
  const previewFields = subFields.filter(f => f.is_preview)
  if (previewFields.length === 0) return fallback
  const parts: string[] = []
  for (const fd of previewFields) {
    let val: unknown
    if (fd.slug in dirty) {
      const d = dirty[fd.slug]
      if (fd.is_localized && typeof d === 'object' && d !== null) {
        val = (d as Record<string, unknown>)[uiLang] ?? Object.values(d as object)[0]
      } else {
        val = d
      }
    } else if (fd.is_localized) {
      const fv = fieldValues.find(v => v.field_slug === fd.slug && v.language === uiLang)
        ?? fieldValues.find(v => v.field_slug === fd.slug)
      val = fv?.value
    } else {
      val = fieldValues.find(v => v.field_slug === fd.slug && v.language === '')?.value
    }
    if (val !== null && val !== undefined && val !== '') parts.push(String(val))
  }
  return parts.length > 0 ? parts.join(' · ') : fallback
}

interface SubmodelChildCardProps {
  item: LocalChild
  subFields: FieldDefinitionOut[]
  subLanguages: string[]
  uiLang: string
  disabled: boolean
  onChange: (dirty: Record<string, unknown>) => void
  onDelete: () => void
  subFieldSeverities?: Record<string, string>
  subFieldMessages?: Record<string, PolicyMessage[]>
}

function SubmodelChildCard({ item, subFields, subLanguages, uiLang, disabled, onChange, onDelete, subFieldSeverities, subFieldMessages }: SubmodelChildCardProps) {
  const hasHighlightedFields = Object.keys(subFieldSeverities ?? {}).length > 0
  const [expanded, setExpanded] = useState(!item.id || hasHighlightedFields)
  const [activeLang, setActiveLang] = useState(subLanguages[0] ?? '')
  const fallbackLabel = item.id ? item.id.slice(0, 8) + '…' : 'New (unsaved)'
  const label = item.id
    ? buildPreviewLabel(subFields, item.saved?.field_values ?? [], item.dirty, uiLang, fallbackLabel)
    : fallbackLabel

  function handleFieldChange(slug: string, lang: string, val: unknown) {
    const subFd = subFields.find(f => f.slug === slug)
    let update: Record<string, unknown>
    if (subFd?.is_localized) {
      const existing = (typeof item.dirty[slug] === 'object' && item.dirty[slug] !== null)
        ? item.dirty[slug] as Record<string, unknown>
        : subLanguages.reduce((acc, l) => {
            acc[l] = getChildFieldValue(item, slug, l)
            return acc
          }, {} as Record<string, unknown>)
      update = { ...item.dirty, [slug]: { ...existing, [lang]: val } }
    } else {
      update = { ...item.dirty, [slug]: val }
    }
    onChange(update)
  }

  const hasChanges = Object.keys(item.dirty).length > 0

  const topSeverity = hasHighlightedFields ? maxSeverity(
    Object.entries(subFieldSeverities ?? {}).flatMap(([, sev]) => [{ level: sev } as PolicyMessage])
  ) : undefined
  const cardBorderColor = item.deleted ? '#fca5a5'
    : (highlightBorderColor(topSeverity, hasChanges) ?? (hasChanges ? '#f9a825' : '#e0e0e0'))
  return (
    <div style={{
      border: `1px solid ${cardBorderColor}`,
      borderRadius: '6px', marginBottom: '0.5rem', background: item.deleted ? '#fef2f2' : '#fafafa',
      ...(hasHighlightedFields ? { boxShadow: '0 0 0 2px rgba(220,38,38,0.15)' } : {}),
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.5rem 0.75rem' }}>
        <span style={{ fontSize: '0.85rem', fontFamily: 'monospace', color: '#555' }}>
          {label}{hasChanges && !item.deleted ? ' *' : ''}{item.deleted ? ' (will be deleted)' : ''}
        </span>
        <div style={{ display: 'flex', gap: '0.4rem' }}>
          {!item.deleted && (
            <>
              <button type="button"
                style={{ fontSize: '0.78rem', padding: '0.2rem 0.5rem', border: '1px solid #ccc', borderRadius: '4px', cursor: 'pointer', background: '#fff' }}
                onClick={() => setExpanded(e => !e)}>
                {expanded ? 'Collapse' : 'Edit'}
              </button>
              {!disabled && (
                <button type="button"
                  style={{ fontSize: '0.78rem', padding: '0.2rem 0.5rem', border: '1px solid #dc2626', borderRadius: '4px', cursor: 'pointer', background: '#fff', color: '#dc2626' }}
                  onClick={onDelete}>
                  Delete
                </button>
              )}
            </>
          )}
          {item.deleted && !disabled && (
            <button type="button"
              style={{ fontSize: '0.78rem', padding: '0.2rem 0.5rem', border: '1px solid #ccc', borderRadius: '4px', cursor: 'pointer', background: '#fff' }}
              onClick={() => onChange({ ...item.dirty, _undelete: true })}>
              Restore
            </button>
          )}
        </div>
      </div>

      {expanded && !item.deleted && (
        <div style={{ padding: '0.5rem 0.75rem', borderTop: '1px solid #e8e8e8' }}>
          {subLanguages.length > 1 && (
            <div style={{ display: 'flex', gap: '0.25rem', marginBottom: '0.5rem' }}>
              {subLanguages.map(l => (
                <button key={l} type="button"
                  style={{ padding: '0.2rem 0.5rem', border: '1px solid #ccc', borderRadius: '4px 4px 0 0', cursor: 'pointer', fontSize: '0.78rem', background: activeLang === l ? '#0066cc' : '#fff', color: activeLang === l ? '#fff' : '#555' }}
                  onClick={() => setActiveLang(l)}>
                  {l}
                </button>
              ))}
            </div>
          )}
          {subFields.map(subFd => {
            const subLabel = getLang(subFd.label as Record<string, string>, uiLang) || subFd.slug
            const langs = subFd.is_localized ? subLanguages.filter(Boolean) : ['']
            const sev = subFieldSeverities?.[subFd.slug]
            const subColor = subFieldColor(sev)
            const subMsgs = subFieldMessages?.[subFd.slug] ?? []
            return (
              <div key={subFd.slug} style={{
                marginBottom: '0.6rem',
                ...(sev ? { outline: `2px solid ${subColor}`, borderRadius: '4px', padding: '0.25rem' } : {}),
              }}>
                <div style={{ fontSize: '0.82rem', fontWeight: 600, color: sev ? subColor : '#444', marginBottom: '0.2rem' }}>
                  {subLabel} <span style={{ fontFamily: 'monospace', fontSize: '0.75rem', color: '#999' }}>({subFd.data_type})</span>
                </div>
                {langs.map(lang => (
                  <FieldInput
                    key={lang || 'nolang'}
                    fd={subFd}
                    value={getChildFieldValue(item, subFd.slug, lang)}
                    onChange={val => handleFieldChange(subFd.slug, lang, val)}
                    disabled={disabled || !!(subFd.type_config as Record<string, unknown>)?.default_current_user}
                    lang={lang}
                    entityChildren={item.saved?.children}
                  />
                ))}
                {subMsgs.length > 0 && <PolicyMessageList messages={subMsgs} />}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

interface SubmodelEditorProps {
  fd: FieldDefinitionOut
  existingChildren: unknown[]    // entity.children[fd.slug]
  existingValue: unknown         // field_values entry value (for submodel_select)
  disabled: boolean
  uiLang: string
  onChange: (ops: SubmodelOp[] | { op: string; fields?: Record<string, unknown> } | null) => void
  subFieldSeverities?: Record<string, string>
  subFieldMessages?: Record<string, PolicyMessage[]>
}

function SubmodelEditor({ fd, existingChildren, existingValue, disabled, uiLang, onChange, subFieldSeverities, subFieldMessages }: SubmodelEditorProps) {
  const isList = fd.data_type === 'submodel_list'
  const subConfig = fd.submodel_config as ConfigVersionOut | null | undefined
  const subFields = subConfig?.fields ?? []
  const subLanguages = (subConfig?.languages ?? []).map(l => l.code)
  if (subLanguages.length === 0) subLanguages.push('')

  // Always keep the latest onChange in a ref so handlers never capture a stale closure
  const onChangeRef = useRef(onChange)
  useEffect(() => { onChangeRef.current = onChange })

  // For submodel_list: manage a list of LocalChild items
  const toItems = (children: unknown[]): LocalChild[] =>
    (children as ChildNode[]).map(c => ({ key: c.id, id: c.id, dirty: {}, saved: c, deleted: false }))

  const [items, setItems] = useState<LocalChild[]>(() => toItems(existingChildren))
  const nextKeyRef = useRef(0)

  // Sync when the server refreshes the entity (existingChildren IDs change after save).
  // Only relevant for submodel_list; the submodel_select branch manages its own
  // pending state below and must NOT emit a list-shaped [] op (which would be
  // written into the single FK column and rejected as "not a valid UUID").
  const prevServerIds = useRef(new Set((existingChildren as ChildNode[]).map(c => c.id)))
  useEffect(() => {
    if (!isList) return
    const incoming = existingChildren as ChildNode[]
    const incomingIds = new Set(incoming.map(c => c.id))
    const same =
      incomingIds.size === prevServerIds.current.size &&
      [...incomingIds].every(id => prevServerIds.current.has(id))
    if (!same) {
      prevServerIds.current = incomingIds
      // Reset to server state — clears any pending-new items that were saved
      setItems(toItems(incoming))
      // After a server refresh there are no pending local ops
      onChangeRef.current([])
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [existingChildren])

  // Helpers that mutate items AND immediately propagate ops — no useEffect lag
  function applyItemChange(newItems: LocalChild[]) {
    setItems(newItems)
    const ops = buildOps(newItems)
    onChangeRef.current(ops.length > 0 ? ops : [])
  }

  function addItem() {
    const key = `_new_${nextKeyRef.current++}`
    applyItemChange([...items, { key, id: null, dirty: {}, saved: null, deleted: false }])
  }

  function updateItem(key: string, dirty: Record<string, unknown>) {
    applyItemChange(items.map(it => it.key === key ? { ...it, dirty, deleted: false } : it))
  }

  function deleteItem(key: string) {
    applyItemChange(
      items
        .map(it => {
          if (it.key !== key) return it
          if (!it.id) return { ...it, deleted: true }
          return { ...it, deleted: true, dirty: {} }
        })
        .filter(it => !(it.deleted && !it.id))
    )
  }

  // For submodel_select: the current op to send (or null = no change)
  const selectNodeId = typeof existingValue === 'string' ? existingValue : null
  const ownedChild = (existingChildren as ChildNode[]).find(c => c.id === selectNodeId) ?? null

  const [selectDirty, setSelectDirty] = useState<Record<string, unknown>>({})
  const [selectActiveLang, setSelectActiveLang] = useState(subLanguages[0] ?? '')
  const [selectExpanded, setSelectExpanded] = useState(false)
  // pendingNew = user clicked "Create", form shown optimistically before save
  const [pendingNew, setPendingNew] = useState(false)
  // pendingRemoval = user clicked Delete/Clear; hide the form before the save round-trip
  const [pendingRemoval, setPendingRemoval] = useState(false)

  // When the entity refreshes after save, clear the pending state
  const prevSelectNodeId = useRef(selectNodeId)
  useEffect(() => {
    if (selectNodeId !== prevSelectNodeId.current) {
      if (pendingNew && selectNodeId) {
        setPendingNew(false)
        setSelectDirty({})
      }
      // FK cleared by the server → drop the optimistic removal flag
      if (!selectNodeId) setPendingRemoval(false)
    }
    prevSelectNodeId.current = selectNodeId
  }, [selectNodeId, pendingNew])

  // ── submodel_list UI ──
  if (isList) {
    const visible = items.filter(it => !(it.deleted && !it.id))

    return (
      <div>
        {visible.length === 0 && (
          <div style={{ fontSize: '0.85rem', color: '#888', fontStyle: 'italic', marginBottom: '0.5rem' }}>No items yet.</div>
        )}
        {visible.map(item => (
          <SubmodelChildCard
            key={item.key}
            item={item}
            subFields={subFields}
            subLanguages={subLanguages}
            uiLang={uiLang}
            disabled={disabled}
            onChange={dirty => updateItem(item.key, dirty)}
            onDelete={() => deleteItem(item.key)}
            subFieldSeverities={subFieldSeverities}
            subFieldMessages={subFieldMessages}
          />
        ))}
        {!disabled && (
          <button type="button"
            style={{ fontSize: '0.82rem', padding: '0.3rem 0.75rem', border: '1px dashed #aaa', borderRadius: '4px', cursor: 'pointer', background: '#fff', color: '#555', marginTop: '0.25rem' }}
            onClick={addItem}>
            + Add item
          </button>
        )}
      </div>
    )
  }

  // ── submodel_select UI ──
  function handleCreate() {
    setPendingNew(true)
    setPendingRemoval(false)
    setSelectDirty({})
    setSelectExpanded(true)
    onChange({ op: 'create', fields: {} })
  }

  function handleCancelPending() {
    setPendingNew(false)
    setSelectDirty({})
    onChange(null)
  }

  function handleDelete() {
    setPendingRemoval(true)
    setSelectExpanded(false)
    onChange({ op: 'delete' })
  }

  function handleClear() {
    setPendingRemoval(true)
    setSelectExpanded(false)
    onChange(null)
  }

  function handleSelectFieldChange(slug: string, lang: string, val: unknown) {
    const subFd = subFields.find(f => f.slug === slug)
    let updated: Record<string, unknown>
    if (subFd?.is_localized) {
      const existing = (typeof selectDirty[slug] === 'object' && selectDirty[slug] !== null)
        ? selectDirty[slug] as Record<string, unknown>
        : subLanguages.reduce((acc, l) => {
            const fv = ownedChild?.field_values.find(v => v.field_slug === slug && v.language === l)
            acc[l] = fv?.value ?? null
            return acc
          }, {} as Record<string, unknown>)
      updated = { ...selectDirty, [slug]: { ...existing, [lang]: val } }
    } else {
      updated = { ...selectDirty, [slug]: val }
    }
    setSelectDirty(updated)
    if (pendingNew) {
      // still creating — carry the fields along with the create op
      onChange({ op: 'create', fields: updated })
    } else if (ownedChild) {
      // submodel_select expects a single dict op, never a list (that is the
      // submodel_list shape and would be written into the FK column).
      onChange({ op: 'update', fields: updated })
    }
  }

  // Show the form when: pending new creation, OR already has a saved/owned child.
  // An optimistic delete/clear hides it immediately.
  const showForm = !pendingRemoval && (pendingNew || ownedChild !== null || selectNodeId !== null)

  return (
    <div style={{ border: '1px solid #e0e0e0', borderRadius: '6px', padding: '0.75rem', background: '#fafafa' }}>
      {!showForm && (
        <div>
          <div style={{ fontSize: '0.85rem', color: '#888', fontStyle: 'italic', marginBottom: '0.5rem' }}>No submodel selected.</div>
          {!disabled && subConfig && (
            <button type="button"
              style={{ fontSize: '0.82rem', padding: '0.3rem 0.75rem', border: '1px dashed #aaa', borderRadius: '4px', cursor: 'pointer', background: '#fff', color: '#555' }}
              onClick={handleCreate}>
              + Create new submodel
            </button>
          )}
          {!disabled && !subConfig && (
            <div style={{ fontSize: '0.82rem', color: '#dc2626' }}>No submodel config assigned to this field.</div>
          )}
        </div>
      )}

      {showForm && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
            <span style={{ fontSize: '0.82rem', fontFamily: 'monospace', color: '#555' }}>
              {pendingNew ? 'New (unsaved)' : buildPreviewLabel(
                subFields,
                ownedChild?.field_values ?? [],
                selectDirty,
                uiLang,
                `${selectNodeId?.slice(0, 8)}…`,
              )}
            </span>
            <div style={{ display: 'flex', gap: '0.4rem' }}>
              {!disabled && (
                <>
                  {!pendingNew && (
                    <button type="button"
                      style={{ fontSize: '0.78rem', padding: '0.2rem 0.5rem', border: '1px solid #ccc', borderRadius: '4px', cursor: 'pointer', background: '#fff' }}
                      onClick={() => setSelectExpanded(e => !e)}>
                      {selectExpanded ? 'Collapse' : 'Edit fields'}
                    </button>
                  )}
                  {pendingNew ? (
                    <button type="button"
                      style={{ fontSize: '0.78rem', padding: '0.2rem 0.5rem', border: '1px solid #aaa', borderRadius: '4px', cursor: 'pointer', background: '#fff', color: '#666' }}
                      onClick={handleCancelPending}>
                      Cancel
                    </button>
                  ) : (
                    <>
                      <button type="button"
                        style={{ fontSize: '0.78rem', padding: '0.2rem 0.5rem', border: '1px solid #dc2626', borderRadius: '4px', cursor: 'pointer', background: '#fff', color: '#dc2626' }}
                        onClick={handleDelete}>
                        Delete
                      </button>
                      <button type="button"
                        style={{ fontSize: '0.78rem', padding: '0.2rem 0.5rem', border: '1px solid #aaa', borderRadius: '4px', cursor: 'pointer', background: '#fff', color: '#666' }}
                        onClick={handleClear}>
                        Clear
                      </button>
                    </>
                  )}
                </>
              )}
            </div>
          </div>

          {(pendingNew || selectExpanded) && subFields.length > 0 && (
            <div style={{ borderTop: '1px solid #e8e8e8', paddingTop: '0.5rem' }}>
              {subLanguages.length > 1 && (
                <div style={{ display: 'flex', gap: '0.25rem', marginBottom: '0.5rem' }}>
                  {subLanguages.map(l => (
                    <button key={l} type="button"
                      style={{ padding: '0.2rem 0.5rem', border: '1px solid #ccc', borderRadius: '4px 4px 0 0', cursor: 'pointer', fontSize: '0.78rem', background: selectActiveLang === l ? '#0066cc' : '#fff', color: selectActiveLang === l ? '#fff' : '#555' }}
                      onClick={() => setSelectActiveLang(l)}>
                      {l}
                    </button>
                  ))}
                </div>
              )}
              {subFields.map(subFd => {
                const subLabel = getLang(subFd.label as Record<string, string>, uiLang) || subFd.slug
                const langs = subFd.is_localized ? subLanguages.filter(Boolean) : ['']
                const sev = subFieldSeverities?.[subFd.slug]
                const subColor = subFieldColor(sev)
                const subMsgs = subFieldMessages?.[subFd.slug] ?? []
                return (
                  <div key={subFd.slug} style={{
                    marginBottom: '0.6rem',
                    ...(sev ? { outline: `2px solid ${subColor}`, borderRadius: '4px', padding: '0.25rem' } : {}),
                  }}>
                    <div style={{ fontSize: '0.82rem', fontWeight: 600, color: sev ? subColor : '#444', marginBottom: '0.2rem' }}>
                      {subLabel} <span style={{ fontFamily: 'monospace', fontSize: '0.75rem', color: '#999' }}>({subFd.data_type})</span>
                    </div>
                    {langs.map(lang => (
                      <FieldInput
                        key={lang || 'nolang'}
                        fd={subFd}
                        value={
                          selectDirty[subFd.slug] !== undefined
                            ? (subFd.is_localized
                                ? (selectDirty[subFd.slug] as Record<string, unknown>)?.[lang]
                                : selectDirty[subFd.slug])
                            : (ownedChild?.field_values.find(v => v.field_slug === subFd.slug && v.language === lang)?.value ?? null)
                        }
                        onChange={val => handleSelectFieldChange(subFd.slug, lang, val)}
                        disabled={disabled}
                        lang={lang}
                        entityChildren={ownedChild?.children}
                      />
                    ))}
                    {subMsgs.length > 0 && <PolicyMessageList messages={subMsgs} />}
                  </div>
                )
              })}
            </div>
          )}

          {!pendingNew && selectExpanded && !ownedChild && (
            <div style={{ fontSize: '0.82rem', color: '#888', fontStyle: 'italic', paddingTop: '0.5rem', borderTop: '1px solid #e8e8e8' }}>
              Referenced submodel is not directly owned by this entity — field editing not available here.
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function UserSelectInput({ value, onChange, disabled, fd }: FieldInputProps) {
  const multi = fd.data_type === 'user_select_multi'
  const groupIds = (fd.type_config as Record<string, unknown>)['limit_to_group_ids']
  const groupIdsStr = Array.isArray(groupIds) ? (groupIds as number[]).join(',') : undefined
  const fetcher = useCallback((q: string) => udmSearchUsers(q, groupIdsStr), [groupIdsStr])
  const ac = useAutocomplete<UserAutocompleteItem>(fetcher)

  const currentIds: string[] = multi
    ? (Array.isArray(value) ? value as string[] : [])
    : (value ? [value as string] : [])

  function selectItem(item: UserAutocompleteItem) {
    if (multi) {
      if (!currentIds.includes(item.id))
        onChange([...currentIds, item.id])
    } else {
      onChange(item.id)
    }
    ac.setQuery('')
    ac.setResults([])
    ac.setOpen(false)
  }

  function removeItem(id: string) {
    if (multi) onChange(currentIds.filter(x => x !== id))
    else onChange(null)
  }

  return (
    <div className={styles.autocompleteWrapper}>
      {!disabled && (
        <input
          className={styles.input}
          value={ac.query}
          onChange={e => ac.search(e.target.value)}
          onBlur={() => setTimeout(() => ac.setOpen(false), 150)}
          placeholder="Search users…"
          disabled={disabled}
        />
      )}
      {ac.open && ac.results.length > 0 && (
        <div className={styles.autocompleteDropdown}>
          {ac.results.map(u => (
            <div key={u.id} className={styles.autocompleteItem} onMouseDown={() => selectItem(u)}>
              {u.display_name}
            </div>
          ))}
        </div>
      )}
      <div className={styles.selectedTags}>
        {currentIds.map(id => {
          const found = ac.results.find(u => u.id === id)
          const label = found ? found.display_name : id
          return (
            <span key={id} className={styles.selectedTag}>
              {label}
              {!disabled && (
                <button type="button" className={styles.removeTag} onClick={() => removeItem(id)}>×</button>
              )}
            </span>
          )
        })}
      </div>
    </div>
  )
}

function GroupSelectInput({ value, onChange, disabled, fd }: FieldInputProps) {
  const multi = fd.data_type === 'group_select_multi'
  const ac = useAutocomplete<GroupAutocompleteItem>(udmSearchGroups)
  const [highlightedIndex, setHighlightedIndex] = useState(-1)
  const [nameMap, setNameMap] = useState<Record<number, string>>({})
  const listboxId = useId()

  const currentIds: number[] = multi
    ? (Array.isArray(value) ? value as number[] : [])
    : (value != null ? [value as number] : [])

  // Populate nameMap from search results as they arrive
  useEffect(() => {
    if (ac.results.length === 0) return
    setNameMap(prev => {
      const next = { ...prev }
      for (const g of ac.results) next[g.id] = g.name
      return next
    })
  }, [ac.results])

  // Fetch names for any selected IDs not yet in the nameMap
  useEffect(() => {
    const missing = currentIds.filter(id => !(id in nameMap))
    if (missing.length === 0) return
    udmSearchGroups('').then(groups => {
      setNameMap(prev => {
        const next = { ...prev }
        for (const g of groups) next[g.id] = g.name
        return next
      })
    }).catch(() => {})
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentIds.join(',')])

  // Reset highlight when results change
  useEffect(() => { setHighlightedIndex(-1) }, [ac.results])

  const filteredResults = ac.results.filter(g => !currentIds.includes(g.id))

  function selectItem(item: GroupAutocompleteItem) {
    setNameMap(prev => ({ ...prev, [item.id]: item.name }))
    if (multi) {
      if (!currentIds.includes(item.id)) onChange([...currentIds, item.id])
    } else {
      onChange(item.id)
    }
    ac.setQuery('')
    ac.setResults([])
    ac.setOpen(false)
    setHighlightedIndex(-1)
  }

  function removeItem(id: number) {
    if (multi) onChange(currentIds.filter(x => x !== id))
    else onChange(null)
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlightedIndex(prev => Math.min(prev + 1, filteredResults.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlightedIndex(prev => Math.max(prev - 1, -1))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (highlightedIndex >= 0 && filteredResults[highlightedIndex]) {
        selectItem(filteredResults[highlightedIndex])
      } else if (filteredResults.length === 1) {
        selectItem(filteredResults[0])
      }
    } else if (e.key === 'Escape') {
      ac.setOpen(false)
      setHighlightedIndex(-1)
    }
  }

  const isOpen = ac.open && filteredResults.length > 0

  return (
    <div className={styles.autocompleteWrapper}>
      {!disabled && (
        <input
          className={styles.input}
          value={ac.query}
          onChange={e => ac.search(e.target.value)}
          onBlur={() => setTimeout(() => { ac.setOpen(false); setHighlightedIndex(-1) }, 150)}
          onKeyDown={handleKeyDown}
          placeholder="Search groups…"
          disabled={disabled}
          role="combobox"
          aria-expanded={isOpen}
          aria-controls={listboxId}
          aria-autocomplete="list"
          aria-activedescendant={highlightedIndex >= 0 ? `${listboxId}-${highlightedIndex}` : undefined}
        />
      )}
      {isOpen && (
        <ul
          id={listboxId}
          role="listbox"
          className={styles.autocompleteDropdown}
          style={{ listStyle: 'none', margin: 0, padding: 0 }}
        >
          {filteredResults.map((g, index) => (
            <li
              key={g.id}
              id={`${listboxId}-${index}`}
              role="option"
              aria-selected={index === highlightedIndex}
              className={`${styles.autocompleteItem}${index === highlightedIndex ? ` ${styles.autocompleteItemHighlighted}` : ''}`}
              onMouseDown={() => selectItem(g)}
              onMouseEnter={() => setHighlightedIndex(index)}
            >
              {g.name}
            </li>
          ))}
        </ul>
      )}
      <div className={styles.selectedTags}>
        {currentIds.map(id => (
          <span key={id} className={styles.selectedTag}>
            {nameMap[id] ?? String(id)}
            {!disabled && (
              <button type="button" className={styles.removeTag} onClick={() => removeItem(id)}>×</button>
            )}
          </span>
        ))}
      </div>
    </div>
  )
}

function EntitySelectInput({ value, onChange, disabled, fd }: FieldInputProps) {
  const multi = fd.data_type === 'entity_select_multi'
  const typeIds = (fd.type_config as Record<string, unknown>)['limit_to_type_ids']
  const typeIdsStr = Array.isArray(typeIds) ? (typeIds as string[]).join(',') : undefined
  const fetcher = useCallback((q: string) => udmSearchEntities(q, typeIdsStr), [typeIdsStr])
  const ac = useAutocomplete<EntityAutocompleteItem>(fetcher)
  const [highlightedIndex, setHighlightedIndex] = useState(-1)
  const [displayMap, setDisplayMap] = useState<Record<string, string>>({})
  const listboxId = useId()

  const currentIds: string[] = multi
    ? (Array.isArray(value) ? value as string[] : [])
    : (value ? [value as string] : [])

  // Persist display strings from search results
  useEffect(() => {
    if (ac.results.length === 0) return
    setDisplayMap(prev => {
      const next = { ...prev }
      for (const e of ac.results) next[e.id] = e.display ?? e.id
      return next
    })
  }, [ac.results])

  // Fetch display strings for pre-selected IDs not yet in the map
  useEffect(() => {
    const missing = currentIds.filter(id => !(id in displayMap))
    if (missing.length === 0) return
    udmSearchEntities('', typeIdsStr, missing.join(',')).then(items => {
      setDisplayMap(prev => {
        const next = { ...prev }
        for (const e of items) next[e.id] = e.display ?? e.id
        return next
      })
    }).catch(() => {})
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentIds.join(',')])

  useEffect(() => { setHighlightedIndex(-1) }, [ac.results])

  const filteredResults = ac.results.filter(e => !currentIds.includes(e.id))

  function selectItem(item: EntityAutocompleteItem) {
    setDisplayMap(prev => ({ ...prev, [item.id]: item.display ?? item.id }))
    if (multi) {
      if (!currentIds.includes(item.id)) onChange([...currentIds, item.id])
    } else {
      onChange(item.id)
    }
    ac.setQuery('')
    ac.setResults([])
    ac.setOpen(false)
    setHighlightedIndex(-1)
  }

  function removeItem(id: string) {
    if (multi) onChange(currentIds.filter(x => x !== id))
    else onChange(null)
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlightedIndex(prev => Math.min(prev + 1, filteredResults.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlightedIndex(prev => Math.max(prev - 1, -1))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (highlightedIndex >= 0 && filteredResults[highlightedIndex]) {
        selectItem(filteredResults[highlightedIndex])
      } else if (filteredResults.length === 1) {
        selectItem(filteredResults[0])
      }
    } else if (e.key === 'Escape') {
      ac.setOpen(false)
      setHighlightedIndex(-1)
    }
  }

  const isOpen = ac.open && filteredResults.length > 0

  return (
    <div className={styles.autocompleteWrapper}>
      {!disabled && (
        <input
          className={styles.input}
          value={ac.query}
          onChange={e => ac.search(e.target.value)}
          onBlur={() => setTimeout(() => { ac.setOpen(false); setHighlightedIndex(-1) }, 150)}
          onKeyDown={handleKeyDown}
          placeholder="Search entities…"
          disabled={disabled}
          role="combobox"
          aria-expanded={isOpen}
          aria-controls={listboxId}
          aria-autocomplete="list"
          aria-activedescendant={highlightedIndex >= 0 ? `${listboxId}-${highlightedIndex}` : undefined}
        />
      )}
      {isOpen && (
        <ul
          id={listboxId}
          role="listbox"
          className={styles.autocompleteDropdown}
          style={{ listStyle: 'none', margin: 0, padding: 0 }}
        >
          {filteredResults.map((e, index) => (
            <li
              key={e.id}
              id={`${listboxId}-${index}`}
              role="option"
              aria-selected={index === highlightedIndex}
              className={`${styles.autocompleteItem}${index === highlightedIndex ? ` ${styles.autocompleteItemHighlighted}` : ''}`}
              onMouseDown={() => selectItem(e)}
              onMouseEnter={() => setHighlightedIndex(index)}
            >
              {e.display ?? e.id}
            </li>
          ))}
        </ul>
      )}
      <div className={styles.selectedTags}>
        {currentIds.map(id => (
          <span key={id} className={styles.selectedTag}>
            {displayMap[id] ?? id}
            {!disabled && (
              <button type="button" className={styles.removeTag} onClick={() => removeItem(id)}>×</button>
            )}
          </span>
        ))}
      </div>
    </div>
  )
}

interface FileFieldProps {
  fd: FieldDefinitionOut
  value: unknown
  onChange: (stagingId: string | null) => void
  disabled: boolean
}

function FileFieldInput({ fd, value, onChange, disabled }: FileFieldProps) {
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [stagingName, setStagingName] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  async function handleFile(file: File) {
    setUploading(true)
    setProgress(0)
    try {
      const staging = await udmUploadStagingFile(file, fd.id, setProgress)
      onChange(staging.staging_id)
      setStagingName(file.name)
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  const currentFile = value && typeof value === 'object' ? value as Record<string, string> : null
  const currentUrl = currentFile?.['url'] ?? null
  const isImage = fd.data_type === 'image'
  const hasValue = stagingName !== null || currentUrl !== null

  function handleClear() {
    setStagingName(null)
    onChange(null)
  }

  return (
    <div>
      {currentUrl && !stagingName && (
        <div className={styles.fileInfo}>
          {isImage ? (
            <img src={currentUrl} alt={currentFile?.['original_name'] ?? 'image'}
              style={{ maxWidth: '100%', maxHeight: '200px', display: 'block', borderRadius: '4px', marginBottom: '0.4rem' }} />
          ) : (
            <a href={currentUrl} target="_blank" rel="noopener noreferrer">
              {currentFile?.['original_name'] ?? 'View file'}
            </a>
          )}
        </div>
      )}
      {stagingName && (
        <div className={styles.fileInfo}>Staged: {stagingName} — will be saved on next save</div>
      )}
      {!disabled && (
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginTop: '0.4rem' }}>
          <div
            className={styles.fileUploadArea}
            style={{ flex: 1, marginTop: 0 }}
            onClick={() => inputRef.current?.click()}
            onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) void handleFile(f) }}
            onDragOver={e => e.preventDefault()}
          >
            {uploading ? `Uploading… ${progress}%` : 'Click or drop to upload'}
          </div>
          {hasValue && (
            <button
              type="button"
              onClick={handleClear}
              style={{ padding: '0.4rem 0.75rem', border: '1px solid #dc2626', borderRadius: '4px', background: '#fff', color: '#dc2626', cursor: 'pointer', fontSize: '0.82rem', whiteSpace: 'nowrap' }}
            >
              Clear
            </button>
          )}
          <input
            ref={inputRef}
            type="file"
            style={{ display: 'none' }}
            accept={fd.data_type === 'image' ? 'image/*' : undefined}
            onChange={e => { const f = e.target.files?.[0]; if (f) void handleFile(f) }}
          />
        </div>
      )}
    </div>
  )
}

function MarkdownFieldInput({ value, onChange, disabled }: FieldInputProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const editorRef = useRef<StacksEditor | null>(null)
  const onChangeRef = useRef(onChange)
  const isSettingContentRef = useRef(false)

  useEffect(() => { onChangeRef.current = onChange })

  useEffect(() => {
    if (!containerRef.current) return
    containerRef.current.innerHTML = ''
    const editor = new StacksEditor(
      containerRef.current,
      (value as string) ?? '',
      { defaultView: EditorType.Commonmark, imageUpload: { handler: undefined } },
    )
    editorRef.current = editor

    function patchDispatch() {
      const view = editor.editorView
      const orig = view.dispatch.bind(view)
      view.dispatch = (tr) => {
        orig(tr)
        if (!isSettingContentRef.current && tr.docChanged) {
          onChangeRef.current(editor.content)
        }
      }
    }
    patchDispatch()

    const target = containerRef.current
    function handleViewChange() { patchDispatch() }
    target.addEventListener('change', handleViewChange)

    if (disabled) editor.disable()

    return () => {
      target.removeEventListener('change', handleViewChange)
      editor.destroy()
      editorRef.current = null
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const editor = editorRef.current
    if (!editor) return
    const incoming = (value as string) ?? ''
    if (incoming !== editor.content) {
      isSettingContentRef.current = true
      editor.content = incoming
      isSettingContentRef.current = false
    }
  }, [value])

  useEffect(() => {
    const editor = editorRef.current
    if (!editor) return
    if (disabled) editor.disable()
    else editor.enable()
  }, [disabled])

  return <div ref={containerRef} className={styles.markdownEditor} />
}

function FieldInput({ fd, value, onChange, disabled, lang = '', entityChildren, subFieldSeverities, subFieldMessages }: FieldInputProps) {
  const dt = fd.data_type
  const tc = fd.type_config as Record<string, unknown>

  if (dt === 'text_short') {
    const maxLen = tc['max_length'] as number | undefined
    const len = ((value as string) ?? '').length
    const over = maxLen !== undefined && len > maxLen
    return (
      <div>
        <input className={styles.input} type="text" value={(value as string) ?? ''}
          onChange={e => onChange(e.target.value)} disabled={disabled}
          maxLength={maxLen} />
        <div className={`${styles.lenHint}${over ? ` ${styles.lenHintOver}` : ''}`}>
          {maxLen !== undefined ? `${len} / ${maxLen}` : len}
        </div>
      </div>
    )
  }

  if (dt === 'text_long') {
    const len = ((value as string) ?? '').length
    return (
      <div>
        <textarea className={styles.textarea} rows={4} value={(value as string) ?? ''}
          onChange={e => onChange(e.target.value)} disabled={disabled} />
        <div className={styles.lenHint}>{len}</div>
      </div>
    )
  }

  if (dt === 'text_markdown') {
    const len = ((value as string) ?? '').length
    return (
      <div>
        <MarkdownFieldInput fd={fd} value={value} onChange={onChange} disabled={disabled} lang={lang} />
        <div className={styles.lenHint}>{len}</div>
      </div>
    )
  }

  if (dt === 'text_richtext') {
    const len = ((value as string) ?? '').length
    return (
      <div>
        <textarea className={styles.textarea} rows={6} value={(value as string) ?? ''}
          onChange={e => onChange(e.target.value)} disabled={disabled}
          style={{ fontFamily: 'inherit' }} />
        <div className={styles.lenHint}>{len}</div>
      </div>
    )
  }

  if (dt === 'slug_id') {
    const prefix = (tc['prefix'] as string) ?? ''
    const display = value != null ? `${prefix}-${value}` : '—'
    return (
      <input className={styles.input} type="text" value={display} disabled readOnly
        style={{ fontFamily: 'monospace', background: '#f5f5f5' }} />
    )
  }

  if (dt === 'integer') {
    return (
      <input className={styles.input} type="number" step="1"
        value={value != null ? String(value) : ''}
        onChange={e => onChange(e.target.value ? parseInt(e.target.value) : null)}
        disabled={disabled} />
    )
  }

  if (dt === 'float') {
    return (
      <input className={styles.input} type="number" step="any"
        value={value != null ? String(value) : ''}
        onChange={e => onChange(e.target.value ? parseFloat(e.target.value) : null)}
        disabled={disabled} />
    )
  }

  if (dt === 'boolean') {
    return (
      <label className={styles.checkbox}>
        <input type="checkbox" checked={!!value}
          onChange={e => onChange(e.target.checked)}
          disabled={disabled} />
        Yes
      </label>
    )
  }

  if (dt === 'date') {
    return (
      <input className={styles.input} type="date" value={(value as string) ?? ''}
        onChange={e => onChange(e.target.value || null)} disabled={disabled} />
    )
  }

  if (dt === 'time') {
    return (
      <input className={styles.input} type="time" value={(value as string) ?? ''}
        onChange={e => onChange(e.target.value || null)} disabled={disabled} />
    )
  }

  if (dt === 'datetime') {
    const iso = value ? (value as string).replace(' ', 'T').slice(0, 16) : ''
    return (
      <input className={styles.input} type="datetime-local" value={iso}
        onChange={e => onChange(e.target.value ? e.target.value + ':00' : null)} disabled={disabled} />
    )
  }

  if (dt === 'select_single') {
    const choices = (tc['choices'] as string[]) ?? []
    return (
      <select className={styles.select} value={(value as string) ?? ''}
        onChange={e => onChange(e.target.value || null)} disabled={disabled}>
        <option value="">— select —</option>
        {choices.map(c => <option key={c} value={c}>{c}</option>)}
      </select>
    )
  }

  if (dt === 'select_multi') {
    const choices = (tc['choices'] as string[]) ?? []
    const selected: string[] = Array.isArray(value) ? value as string[] : []
    return (
      <div>
        {choices.map(c => (
          <label key={c} className={styles.checkbox} style={{ marginBottom: '0.25rem' }}>
            <input type="checkbox" disabled={disabled}
              checked={selected.includes(c)}
              onChange={e => {
                if (e.target.checked) onChange([...selected, c])
                else onChange(selected.filter(x => x !== c))
              }} />
            {c}
          </label>
        ))}
      </div>
    )
  }

  if (dt === 'user_select' || dt === 'user_select_multi') {
    return <UserSelectInput fd={fd} value={value} onChange={onChange} disabled={disabled} lang={lang} />
  }

  if (dt === 'group_select' || dt === 'group_select_multi') {
    return <GroupSelectInput fd={fd} value={value} onChange={onChange} disabled={disabled} lang={lang} />
  }

  if (dt === 'entity_select' || dt === 'entity_select_multi') {
    return <EntitySelectInput fd={fd} value={value} onChange={onChange} disabled={disabled} lang={lang} />
  }

  if (dt === 'image' || dt === 'file') {
    return (
      <FileFieldInput
        fd={fd}
        value={value}
        disabled={disabled}
        onChange={stagingId => onChange(stagingId ? { staging_id: stagingId } : null)}
      />
    )
  }

  if (dt === 'submodel_list' || dt === 'submodel_select') {
    // value for submodel_list = ops array (from dirty) or ignored (use entityChildren)
    // value for submodel_select = node UUID string or null
    return (
      <SubmodelEditor
        fd={fd}
        existingChildren={(entityChildren?.[fd.slug] ?? []) as unknown[]}
        existingValue={value}
        disabled={disabled}
        uiLang={lang || 'en'}
        onChange={onChange as (ops: unknown) => void}
        subFieldSeverities={subFieldSeverities}
        subFieldMessages={subFieldMessages}
      />
    )
  }

  // Fallback: JSON display
  return (
    <input className={styles.input} value={JSON.stringify(value) ?? ''}
      onChange={e => { try { onChange(JSON.parse(e.target.value)) } catch { onChange(e.target.value) } }}
      disabled={disabled} />
  )
}

// ── Workflow field widget ─────────────────────────────────────────────────────

interface WorkflowFieldWidgetProps {
  fd: FieldDefinitionOut
  entity: EntityOut
  uiLang: string
  onTransition: (fieldSlug: string, transitionName: string) => Promise<void>
  transitioning: boolean
  messages?: PolicyMessage[]
}

function WorkflowFieldWidget({ fd, entity, uiLang, onTransition, transitioning, messages }: WorkflowFieldWidgetProps) {
  const wfDef = (fd as FieldDefinitionOut & { workflow_definition?: WorkflowDefinitionOut | null }).workflow_definition
  const fv = entity.field_values.find(v => v.field_slug === fd.slug)
  const currentStateName = (fv?.value as string | null) ?? null

  const label = getLang(fd.label as Record<string, string>, uiLang) || fd.slug
  const helpText = getLang(fd.help_text as Record<string, string>, uiLang)

  const currentState = wfDef?.states.find(s => s.name === currentStateName) ?? null
  const stateLabel = currentState
    ? getLang(currentState.label as Record<string, string>, uiLang) || currentStateName
    : currentStateName

  // Mirror engine.py transition gate exactly
  const availableTransitions: WorkflowTransitionOut[] = (wfDef?.transitions ?? []).filter(t => {
    if (t.from_undefined_only) return currentStateName === null
    if (t.from_state !== null) return t.from_state === currentStateName
    return true // from_state null, not from_undefined_only → always available
  })

  return (
    <div className={styles.fieldGroup}>
      <div className={styles.fieldHeader}>
        <div>
          <div className={styles.fieldLabel}>{label}</div>
          <div className={styles.fieldSlug}>{fd.slug} · workflow</div>
          {helpText && <div className={styles.fieldHelp}>{helpText}</div>}
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
        <span style={{
          display: 'inline-block',
          padding: '0.2rem 0.6rem',
          borderRadius: '4px',
          fontSize: '0.85rem',
          fontWeight: 600,
          background: currentStateName ? '#dbeafe' : '#f1f5f9',
          color: currentStateName ? '#1d4ed8' : '#64748b',
          border: '1px solid',
          borderColor: currentStateName ? '#93c5fd' : '#cbd5e1',
        }}>
          {stateLabel ?? '(no state)'}
        </span>
        {availableTransitions.map(t => {
          const tLabel = getLang(t.label as Record<string, string>, uiLang) || t.name
          return (
            <button
              key={t.name}
              type="button"
              className={styles.transitionBtn}
              disabled={transitioning}
              onClick={() => void onTransition(fd.slug, t.name)}
            >
              {tLabel}
            </button>
          )
        })}
        {availableTransitions.length === 0 && (
          <span style={{ fontSize: '0.82rem', color: '#888', fontStyle: 'italic' }}>No transitions available</span>
        )}
      </div>
      {messages && messages.length > 0 && (
        <div style={{ marginTop: '0.5rem' }}>
          <PolicyMessageList messages={messages} />
        </div>
      )}
    </div>
  )
}

// ── Field row ─────────────────────────────────────────────────────────────────

interface FieldRowProps {
  fd: FieldDefinitionOut
  entity: EntityOut
  dirty: Record<string, unknown>
  onDirty: (slug: string, val: unknown) => void
  onReset: (slug: string) => void
  editable: boolean
  languages: string[]
  uiLang: string
  severity?: string
  messages?: PolicyMessage[]
  subFieldSeverities?: Record<string, string>
  subFieldMessages?: Record<string, PolicyMessage[]>
  onTransition: (fieldSlug: string, transitionName: string) => Promise<void>
  transitioning: boolean
}

function FieldRow({ fd, entity, dirty, onDirty, onReset, editable, languages, uiLang, severity, messages, subFieldSeverities, subFieldMessages, onTransition, transitioning }: FieldRowProps) {
  const [activeLang, setActiveLang] = useState(languages[0] ?? '')
  const isDirty = fd.slug in dirty
  const isSubmodel = fd.data_type === 'submodel_list' || fd.data_type === 'submodel_select'

  // Workflow fields are fully managed by WorkflowFieldWidget — no dirty/value editing
  if (fd.data_type === 'workflow') {
    return <WorkflowFieldWidget fd={fd} entity={entity} uiLang={uiLang} onTransition={onTransition} transitioning={transitioning} messages={messages} />
  }
  const label = getLang(fd.label as Record<string, string>, uiLang) || fd.slug
  const helpText = getLang(fd.help_text as Record<string, string>, uiLang)

  function getVal(lang = '') {
    if (isDirty) {
      const d = dirty[fd.slug]
      if (fd.is_localized && typeof d === 'object' && d !== null)
        return (d as Record<string, unknown>)[lang]
      return d
    }
    return getFieldValue(entity, fd.slug, lang)
  }

  function handleChange(lang: string, val: unknown) {
    if (isSubmodel) {
      // submodel ops passed directly — no localized wrapping
      onDirty(fd.slug, val)
      return
    }
    if (fd.is_localized) {
      const existing = isDirty && typeof dirty[fd.slug] === 'object' && dirty[fd.slug] !== null
        ? (dirty[fd.slug] as Record<string, unknown>)
        : getAllLangValues(entity, fd.slug)
      onDirty(fd.slug, { ...existing, [lang]: val })
    } else {
      onDirty(fd.slug, val)
    }
  }

  // For submodel_list: isDirty shows whether ops are pending; value is always from entity.children
  const submodelHasChanges = isSubmodel && isDirty && (() => {
    const v = dirty[fd.slug]
    if (Array.isArray(v)) return v.length > 0
    if (v && typeof v === 'object') return true
    return v !== null && v !== undefined
  })()

  const fieldIsDirty = (isDirty && !isSubmodel) || submodelHasChanges
  const highlightClass = (() => {
    if (!severity) return fieldIsDirty ? styles.fieldGroupDirty : ''
    if (severity === 'error' || severity === 'critical') return styles.fieldGroupError
    if (fieldIsDirty) return styles.fieldGroupDirty
    if (severity === 'warning') return styles.fieldGroupWarning
    return styles.fieldGroupInfo
  })()
  return (
    <div className={`${styles.fieldGroup} ${highlightClass}`}>
      <div className={styles.fieldHeader}>
        <div>
          <div className={styles.fieldLabel}>{label}</div>
          <div className={styles.fieldSlug}>{fd.slug} · {fd.data_type}</div>
          {helpText && <div className={styles.fieldHelp}>{helpText}</div>}
        </div>
        {(isDirty && !isSubmodel) && (
          <div className={styles.fieldActions}>
            <button type="button" className={styles.resetBtn} onClick={() => onReset(fd.slug)}>
              Reset
            </button>
          </div>
        )}
      </div>

      {!isSubmodel && fd.is_localized && languages.length > 1 && (
        <div className={styles.langTabs}>
          {languages.map(l => (
            <button key={l} type="button"
              className={`${styles.langTab} ${activeLang === l ? styles.langTabActive : ''}`}
              onClick={() => setActiveLang(l)}>
              {l}
            </button>
          ))}
        </div>
      )}

      {isSubmodel ? (
        // Submodels always receive full entity.children context; value = FK UUID for submodel_select
        <FieldInput
          fd={fd}
          value={getFieldValue(entity, fd.slug, '')}
          onChange={val => handleChange('', val)}
          disabled={!editable}
          lang={uiLang}
          entityChildren={entity.children as Record<string, unknown[]>}
          subFieldSeverities={subFieldSeverities}
          subFieldMessages={subFieldMessages}
        />
      ) : fd.is_localized ? (
        <FieldInput
          fd={fd}
          value={getVal(activeLang)}
          onChange={val => handleChange(activeLang, val)}
          disabled={!editable}
          lang={activeLang}
        />
      ) : (
        <FieldInput
          fd={fd}
          value={getVal()}
          onChange={val => handleChange('', val)}
          disabled={!editable}
        />
      )}
      {messages && messages.length > 0 && <PolicyMessageList messages={messages} />}
    </div>
  )
}

// ── Policy message rendering ───────────────────────────────────────────────────

const MSG_COLORS: Record<string, { text: string; bg: string }> = {
  critical: { text: '#991b1b', bg: '#fef2f2' },
  error:    { text: '#991b1b', bg: '#fef2f2' },
  warning:  { text: '#92400e', bg: '#fffbeb' },
  info:     { text: '#1e40af', bg: '#eff6ff' },
}

function PolicyMessageList({ messages }: { messages: PolicyMessage[] }) {
  return (
    <ul style={{ margin: '0.4rem 0 0', padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
      {messages.map((m, i) => {
        const color = MSG_COLORS[m.level] ?? MSG_COLORS.info
        return (
          <li key={i} style={{
            fontSize: '0.8rem', padding: '0.2rem 0.5rem',
            borderRadius: '4px', color: color.text, background: color.bg,
          }}>
            {m.text}
          </li>
        )
      })}
    </ul>
  )
}

// ── Transition message popup ──────────────────────────────────────────────────

function TransitionMessagePopup({ messages, onClose }: { messages: PolicyMessage[]; onClose: () => void }) {
  return (
    <div
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.35)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: '#fff', borderRadius: '8px', padding: '1.5rem',
          maxWidth: '440px', width: '90%', boxShadow: '0 8px 32px rgba(0,0,0,0.18)',
        }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <span style={{ fontWeight: 600, fontSize: '0.95rem' }}>Transition messages</span>
          <button
            type="button"
            onClick={onClose}
            style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '1.2rem', color: '#888', lineHeight: 1, padding: '0 0.2rem' }}
            aria-label="Close"
          >
            ×
          </button>
        </div>
        <PolicyMessageList messages={messages} />
        <div style={{ marginTop: '1rem', textAlign: 'right' }}>
          <button
            type="button"
            onClick={onClose}
            style={{ padding: '0.4rem 1rem', background: '#f5f5f5', border: '1px solid #ccc', borderRadius: '4px', cursor: 'pointer', fontSize: '0.875rem' }}
          >
            OK
          </button>
        </div>
      </div>
    </div>
  )
}

// ── History panel ─────────────────────────────────────────────────────────────

function HistoryPanel({ entityId }: { entityId: string }) {
  const [history, setHistory] = useState<EditHistoryOut | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    udmEntityHistory(entityId)
      .then(h => setHistory(h))
      .catch(() => setHistory(null))
      .finally(() => setLoading(false))
  }, [entityId])

  if (loading) return <div>Loading history…</div>
  if (!history || history.results.length === 0)
    return <div style={{ color: '#888', fontSize: '0.875rem' }}>No edit history yet.</div>

  return (
    <div>
      {history.results.map(group => (
        <div key={group.id} className={styles.historyGroup}>
          <div className={styles.historyMeta}>
            {new Date(group.saved_at).toLocaleString()}{' '}
            {group.saved_by ? `by ${group.saved_by.display_name}` : ''}
            {' · '}{group.node_type}
          </div>
          {group.edits.map((edit, i) => (
            <div key={i} className={styles.historyEdit}>
              {edit.change_kind === 'field_value' ? (
                <span>
                  <strong>{edit.field_label ?? edit.field_slug}</strong>
                  {edit.language ? (
                    <span style={{ fontFamily: 'monospace', fontSize: '0.72rem', background: '#f0f0f0', borderRadius: '3px', padding: '0.05rem 0.3rem', marginLeft: '0.3rem', color: '#555' }}>
                      {edit.language}
                    </span>
                  ) : null}
                  {': '}
                  {edit.old_file_name
                    ? <>{edit.old_file_name} → {edit.new_file_name ?? '—'}</>
                    : <>{JSON.stringify(edit.old_value)} → {JSON.stringify(edit.new_value)}</>
                  }
                </span>
              ) : edit.change_kind === 'node_transition' ? (
                <span>
                  <strong>{edit.field_label ?? edit.field_slug}</strong>:{' '}
                  {(edit.old_value as Record<string, unknown> | null)?.state as string ?? '—'}
                  {' → '}
                  {(edit.new_value as Record<string, unknown> | null)?.state as string ?? '—'}
                </span>
              ) : edit.change_kind === 'node_added' ? (
                <span>+ <strong>{edit.field_label ?? edit.field_slug}</strong> item added</span>
              ) : edit.change_kind === 'node_removed' ? (
                <span>− <strong>{edit.field_label ?? edit.field_slug}</strong> item removed</span>
              ) : edit.change_kind === 'node_reordered' ? (
                <span>
                  <strong>{edit.field_label ?? edit.field_slug}</strong> reordered:{' '}
                  {(edit.old_value as Record<string, unknown> | null)?.sort_order as number}
                  {' → '}
                  {(edit.new_value as Record<string, unknown> | null)?.sort_order as number}
                </span>
              ) : (
                <span>{edit.change_kind}</span>
              )}
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

// ── Main entity editor ────────────────────────────────────────────────────────

export function UdmEntityEditor() {
  const { entityId } = useParams<{ entityId: string }>()
  const navigate = useNavigate()
  const { i18n } = useTranslation()

  const [entity, setEntity] = useState<EntityOut | null>(null)
  const [config, setConfig] = useState<ConfigVersionOut | null>(null)
  const [dirty, setDirty] = useState<Record<string, unknown>>({})
  const [saving, setSaving] = useState(false)
  const [transitioning, setTransitioning] = useState(false)
  const [errors, setErrors] = useState<string[]>([])
  const [success, setSuccess] = useState<string | null>(null)
  const [showHistory, setShowHistory] = useState(false)
  const [policyMessages, setPolicyMessages] = useState<PolicyMessage[]>([])
  const [transitionPopup, setTransitionPopup] = useState<PolicyMessage[]>([])

  const fieldSeverities = useMemo(() => {
    const out: Record<string, string> = {}
    for (const m of policyMessages) {
      for (const p of m.highlight_fields ?? []) {
        const slug = p.split('.')[0]
        if (!out[slug] || SEVERITY_ORDER.indexOf(m.level) > SEVERITY_ORDER.indexOf(out[slug]))
          out[slug] = m.level
      }
    }
    return out
  }, [policyMessages])

  const subFieldSeverities = useMemo(() => {
    const out: Record<string, Record<string, string>> = {}
    for (const m of policyMessages) {
      for (const p of m.highlight_fields ?? []) {
        const dot = p.indexOf('.')
        if (dot === -1) continue
        const parent = p.slice(0, dot); const child = p.slice(dot + 1)
        const parentMap = (out[parent] ??= {})
        if (!parentMap[child] || SEVERITY_ORDER.indexOf(m.level) > SEVERITY_ORDER.indexOf(parentMap[child]))
          parentMap[child] = m.level
      }
    }
    return out
  }, [policyMessages])

  // Messages keyed by top-level slug (for rendering below each FieldRow)
  const fieldMessages = useMemo(() => {
    const out: Record<string, PolicyMessage[]> = {}
    for (const m of policyMessages)
      for (const p of m.highlight_fields ?? []) {
        const slug = p.split('.')[0]
        ;(out[slug] ??= []).includes(m) || out[slug].push(m)
      }
    return out
  }, [policyMessages])

  // Messages with no field assignment — shown near the save button
  const globalPolicyMessages = useMemo(
    () => policyMessages.filter(m => !m.highlight_fields?.length),
    [policyMessages],
  )

  // Messages keyed by parent slug → child slug (for rendering below sub-fields)
  const subFieldMessages = useMemo(() => {
    const out: Record<string, Record<string, PolicyMessage[]>> = {}
    for (const m of policyMessages)
      for (const p of m.highlight_fields ?? []) {
        const dot = p.indexOf('.')
        if (dot === -1) continue
        const parent = p.slice(0, dot); const child = p.slice(dot + 1)
        ;((out[parent] ??= {})[child] ??= []).push(m)
      }
    return out
  }, [policyMessages])

  const uiLang = i18n.language.split('-')[0]

  const load = useCallback(async () => {
    if (!entityId) return
    try {
      const e = await udmGetEntity(entityId)
      setEntity(e)
      // Load the entity's ACTUAL pinned config version (not the type's current
      // published config). This keeps the form aligned with the stored data even
      // when the entity is stuck on an archived version awaiting migration.
      const cfg = await udmGetConfigVersion(e.config_version_id)
      setConfig(cfg)
      // Run save policy with no pending changes to surface ambient warnings
      // (rules that inspect input.entity.fields rather than input.changed_fields).
      try {
        const validation = await udmValidateEntity(entityId, {})
        setPolicyMessages(validation.policy_messages ?? [])
      } catch { /* validation is best-effort */ }
    } catch (err) {
      if (err instanceof UdmApiError && err.policyMessages.length > 0) {
        setPolicyMessages(err.policyMessages)
      }
      setErrors([err instanceof Error ? err.message : 'Failed to load entity'])
    }
  }, [entityId])

  useEffect(() => { void load() }, [load])

  const pendingValidation = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => {
    if (!entityId || Object.keys(dirty).length === 0) {
      setPolicyMessages([])
      return
    }
    if (pendingValidation.current) clearTimeout(pendingValidation.current)
    pendingValidation.current = setTimeout(async () => {
      try {
        const result = await udmValidateEntity(entityId, dirty)
        setPolicyMessages(result.policy_messages ?? [])
      } catch {
        // Validation is best-effort — ignore lock conflicts and network errors
      }
    }, 600)
    return () => {
      if (pendingValidation.current) clearTimeout(pendingValidation.current)
    }
  }, [dirty, entityId])

  if (!entity || !entityId) {
    return (
      <div className={styles.page}>
        {errors.length > 0
          ? <div className={styles.error}>{errors.map((m, i) => <div key={i}>{m}</div>)}</div>
          : <div>Loading…</div>}
        {policyMessages.length > 0 && (
          <div style={{ marginTop: '1rem' }}>
            <PolicyMessageList messages={policyMessages} />
          </div>
        )}
      </div>
    )
  }
  // entityId is now narrowed to string (not undefined) below this point
  const resolvedEntityId: string = entityId

  // An entity pinned to a non-published (archived) config version is read-only
  // until it is migrated to the current version.
  const isArchived = config?.status === 'archived'

  // Determine editability: archived overrides everything; otherwise defer to
  // the per-field editable_fields list returned by the policy.
  const editable = !isArchived
  const editableFieldSlugs: Set<string> | null =
    entity.editable_fields != null ? new Set(entity.editable_fields) : null

  const languages = (config?.languages ?? []).map(l => l.code)
  if (languages.length === 0) languages.push('')

  const allFields = config?.fields ?? []
  const viewableFieldSlugs = entity.viewable_fields ? new Set(entity.viewable_fields) : null
  const fields = viewableFieldSlugs
    ? allFields.filter(fd => viewableFieldSlugs.has(fd.slug))
    : allFields

  function handleDirty(slug: string, val: unknown) {
    setDirty(prev => ({ ...prev, [slug]: val }))
    setSuccess(null)
  }

  function handleReset(slug: string) {
    setDirty(prev => {
      const n = { ...prev }
      delete n[slug]
      return n
    })
  }

  async function handleSave() {
    if (Object.keys(dirty).length === 0) return
    if (pendingValidation.current) clearTimeout(pendingValidation.current)
    setSaving(true)
    setErrors([])
    setSuccess(null)
    try {
      const updated = await udmPatchEntity(resolvedEntityId, dirty)
      setEntity(updated)
      setDirty({})
      setPolicyMessages(updated.policy_messages ?? [])
      setSuccess('Saved successfully.')
    } catch (e) {
      if (e instanceof UdmApiError) {
        const plainErrors: string[] = [
          ...e.pydanticErrors.map(err => {
            const loc = err.loc.filter(s => s !== 'body' && s !== 'payload').join(' → ')
            return loc ? `${loc}: ${err.msg}` : err.msg
          }),
          ...Object.entries(e.fieldErrors).flatMap(([field, errs]) =>
            errs.map(err => (field === '__all__' ? err : `${field}: ${err}`)),
          ),
        ]
        // Fall back to the raw message only when there is no structured data at all
        if (plainErrors.length === 0 && e.policyMessages.length === 0) plainErrors.push(e.message)
        setErrors(plainErrors)
        setPolicyMessages(e.policyMessages)
      } else {
        setErrors([e instanceof Error ? e.message : 'Save failed'])
      }
    } finally {
      setSaving(false)
    }
  }

  async function handleTransition(fieldSlug: string, transitionName: string) {
    setTransitioning(true)
    setErrors([])
    setSuccess(null)
    try {
      const updated = await udmTransitionEntity(resolvedEntityId, fieldSlug, transitionName, dirty)
      setEntity(updated)
      setDirty({})
      setPolicyMessages(updated.policy_messages ?? [])
      const globalMsgs = (updated.policy_messages ?? []).filter((m: PolicyMessage) => !m.highlight_fields?.length)
      if (globalMsgs.length > 0) {
        setTransitionPopup(globalMsgs)
      } else {
        setSuccess(`Transition "${transitionName}" applied.`)
      }
    } catch (e) {
      if (e instanceof UdmApiError) {
        const globalMsgs = e.policyMessages.filter(m => !m.highlight_fields?.length)
        if (globalMsgs.length > 0) {
          setTransitionPopup(globalMsgs)
        } else {
          const plainErrors = e.allMessages
          setErrors(plainErrors.length > 0 ? plainErrors : ['Transition failed'])
        }
      } else {
        setErrors([e instanceof Error ? e.message : 'Transition failed'])
      }
    } finally {
      setTransitioning(false)
    }
  }

  const dirtyCount = Object.keys(dirty).length

  return (
    <div className={styles.page}>
      {transitionPopup.length > 0 && (
        <TransitionMessagePopup messages={transitionPopup} onClose={() => setTransitionPopup([])} />
      )}
      <div className={styles.header}>
        <button type="button" className={styles.backBtn} onClick={() => navigate(-1)}>
          ← Back
        </button>
        <h1 className={styles.pageTitle}>
          Entity
          <span className={styles.metaInfo} style={{ marginLeft: '0.75rem', display: 'inline' }}>
            {entityId.slice(0, 8)}…
          </span>
        </h1>
      </div>

      <div className={styles.metaInfo}>
        Type: {entity.user_defined_model_type_id ?? '—'} ·
        Created: {new Date(entity.created_at).toLocaleString()} ·
        Updated: {new Date(entity.updated_at).toLocaleString()}
        {config && ` · Config version: ${entity.config_version_id.slice(0, 8)}…`}
      </div>

      {isArchived && (
        <MigrationAssistant
          entityId={resolvedEntityId}
          targetTypeId={entity.user_defined_model_type_id}
          sourceConfig={config}
          onMigrated={updated => { setEntity(updated); setDirty({}); void load() }}
        />
      )}

      {/* Dynamic form */}
      {fields.length === 0 && (
        <div style={{ color: '#888', fontStyle: 'italic', padding: '1rem' }}>
          {config ? 'This config has no fields defined.' : 'No config loaded for this entity type.'}
        </div>
      )}

      <div className={styles.form}>
        {fields.map(fd => (
          <FieldRow
            key={fd.slug}
            fd={fd}
            entity={entity}
            dirty={dirty}
            onDirty={handleDirty}
            onReset={handleReset}
            editable={editable && (editableFieldSlugs == null || editableFieldSlugs.has(fd.slug))}
            languages={fd.is_localized ? languages.filter(Boolean) : ['']}
            uiLang={uiLang}
            severity={fieldSeverities[fd.slug]}
            messages={fieldMessages[fd.slug]}
            subFieldSeverities={subFieldSeverities[fd.slug]}
            subFieldMessages={subFieldMessages[fd.slug]}
            onTransition={handleTransition}
            transitioning={transitioning}
          />
        ))}
      </div>

      <div className={styles.toolbar}>
        <div style={{ fontSize: '0.875rem', color: '#888' }}>
          {dirtyCount > 0 ? `${dirtyCount} unsaved change${dirtyCount > 1 ? 's' : ''}` : 'No changes'}
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          {dirtyCount > 0 && (
            <button type="button" className={`${styles.btn} ${styles.btnSecondary}`}
              onClick={() => setDirty({})}>
              Discard All
            </button>
          )}
          <button type="button" className={`${styles.btn} ${styles.btnSecondary}`}
            onClick={() => setShowHistory(!showHistory)}>
            {showHistory ? 'Hide History' : 'View History'}
          </button>
          <button type="button" className={`${styles.btn} ${styles.btnPrimary}`}
            onClick={handleSave} disabled={saving || dirtyCount === 0 || !editable}>
            {saving ? 'Saving…' : 'Save Changes'}
          </button>
        </div>
      </div>

      {errors.length > 0 && (
        <div className={styles.error} style={{ marginTop: '0.5rem' }}>
          {errors.map((msg, i) => <div key={i}>{msg}</div>)}
        </div>
      )}
      {globalPolicyMessages.length > 0 && (
        <div style={{ marginTop: '0.5rem' }}>
          <PolicyMessageList messages={globalPolicyMessages} />
        </div>
      )}
      {success && <div className={styles.success} style={{ marginTop: '0.5rem' }}>{success}</div>}

      {showHistory && (
        <div className={styles.historySection}>
          <div className={styles.historyTitle}>Edit History</div>
          <HistoryPanel entityId={resolvedEntityId} />
        </div>
      )}
    </div>
  )
}

// ── Entity selector / create panel ───────────────────────────────────────────

export function UdmEntityPanel() {
  const navigate = useNavigate()
  const [types, setTypes] = useState<import('./apiUdm').UDMTypeOut[]>([])
  const [entities, setEntities] = useState<import('./apiUdm').EntityAutocompleteItem[]>([])
  const [filterTypeId, setFilterTypeId] = useState('')
  const [selectedEntityId, setSelectedEntityId] = useState('')
  const [createTypeId, setCreateTypeId] = useState('')
  const [creating, setCreating] = useState(false)
  const [loadingEntities, setLoadingEntities] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    import('./apiUdm').then(({ udmListTypes }) => {
      udmListTypes().then(setTypes).catch(() => {})
    })
  }, [])

  // Reload entity list when type filter changes
  useEffect(() => {
    setLoadingEntities(true)
    setSelectedEntityId('')
    import('./apiUdm').then(({ udmSearchEntities }) => {
      udmSearchEntities('', filterTypeId || undefined)
        .then(setEntities)
        .catch(() => setEntities([]))
        .finally(() => setLoadingEntities(false))
    })
  }, [filterTypeId])

  async function handleCreate() {
    if (!createTypeId) { setError('Select a UDM type'); return }
    setCreating(true)
    setError(null)
    try {
      const { udmCreateEntity } = await import('./apiUdm')
      const e = await udmCreateEntity({ user_defined_model_type_id: createTypeId })
      navigate(`/udm-entity/${e.id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Create failed')
    } finally {
      setCreating(false)
    }
  }

  function handleOpen() {
    if (!selectedEntityId) { setError('Select an entity'); return }
    navigate(`/udm-entity/${selectedEntityId}`)
  }

  const panelStyle: React.CSSProperties = {
    background: '#fff', border: '1px solid #e0e0e0', borderRadius: '8px', padding: '1.25rem', marginBottom: '1rem',
  }
  const selectStyle: React.CSSProperties = {
    width: '100%', padding: '0.45rem 0.7rem', border: '1px solid #ccc',
    borderRadius: '4px', marginBottom: '0.5rem', boxSizing: 'border-box', fontSize: '0.9rem', background: '#fff',
  }

  return (
    <div style={{ padding: '2rem', maxWidth: '560px', margin: '0 auto' }}>
      <h2 style={{ fontWeight: 600, marginBottom: '1.5rem' }}>UDM Entities</h2>

      <div style={panelStyle}>
        <div style={{ fontWeight: 600, marginBottom: '0.75rem' }}>Open Existing Entity</div>
        <label style={{ fontSize: '0.82rem', color: '#666', display: 'block', marginBottom: '0.25rem' }}>
          Filter by type (optional)
        </label>
        <select style={selectStyle} value={filterTypeId} onChange={e => setFilterTypeId(e.target.value)}>
          <option value="">— all types —</option>
          {types.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
        <label style={{ fontSize: '0.82rem', color: '#666', display: 'block', marginBottom: '0.25rem' }}>
          Entity {loadingEntities ? '(loading…)' : `(${entities.length} found)`}
        </label>
        <select style={selectStyle} value={selectedEntityId}
          onChange={e => setSelectedEntityId(e.target.value)}
          disabled={loadingEntities}>
          <option value="">— select entity —</option>
          {entities.map(e => (
            <option key={e.id} value={e.id}>
              {e.display && e.display !== e.id ? `${e.display} (${e.id.slice(0, 8)}…)` : e.id}
            </option>
          ))}
        </select>
        {error && <div style={{ color: '#dc2626', fontSize: '0.85rem', marginBottom: '0.5rem' }}>{error}</div>}
        <button
          style={{ padding: '0.45rem 1rem', background: '#0066cc', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer', opacity: !selectedEntityId ? 0.5 : 1 }}
          onClick={handleOpen} disabled={!selectedEntityId}>
          Open
        </button>
      </div>

      <div style={panelStyle}>
        <div style={{ fontWeight: 600, marginBottom: '0.75rem' }}>Create New Entity</div>
        {types.length === 0 ? (
          <div style={{ color: '#888', fontSize: '0.875rem', marginBottom: '0.5rem' }}>
            No UDM types available. Create types in the UDM Admin page first.
          </div>
        ) : (
          <select style={selectStyle} value={createTypeId} onChange={e => setCreateTypeId(e.target.value)}>
            <option value="">— select type —</option>
            {types.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
        )}
        <button
          style={{ padding: '0.45rem 1rem', background: '#16a34a', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer', opacity: creating || !createTypeId ? 0.5 : 1 }}
          onClick={handleCreate} disabled={creating || !createTypeId}>
          {creating ? 'Creating…' : 'Create Entity'}
        </button>
      </div>
    </div>
  )
}
