import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { UdmApiError } from './apiUdm'
import {
  udmListConfigs,
  udmCreateConfig,
  udmUpdateConfig,
  udmDeleteConfig,
  udmGetDraftVersion,
  udmGetPublishedVersion,
  udmReplaceDraft,
  udmPublishDraft,
  udmListPolicies,
  udmCreatePolicy,
  udmUpdatePolicy,
  udmDeletePolicy,
  udmUpdateType,
  udmListTypePolicies,
  udmAssignPolicy,
  udmRemovePolicy,
  udmListTypes,
  udmCreateType,
  udmSearchEntities,
  udmSearchUsers,
  udmEvalPolicy,
  type FieldConfigOut,
  type ConfigVersionOut,
  type FieldDefinitionIn,
  type FieldDefinitionOut,
  type PolicyOut,
  type UDMTypeOut,
  type DataType,
  type AnyRuleIn,
  type PolicyEvalOut,
  type EntityAutocompleteItem,
  type UserAutocompleteItem,
} from './apiUdm'
import { usePermissions } from './usePermissions'
import styles from './UdmAdminPage.module.css'

type AdminTab = 'configs' | 'policies' | 'types'
type ConfigView = 'list' | 'detail'

const DATA_TYPES: DataType[] = [
  'text_short', 'text_long', 'text_markdown', 'text_richtext',
  'integer', 'float', 'boolean', 'date', 'time', 'datetime',
  'select_single', 'select_multi', 'image', 'file',
  'user_select', 'user_select_multi', 'group_select', 'group_select_multi',
  'submodel_select', 'submodel_list', 'entity_select', 'entity_select_multi',
]

// ── Helpers ───────────────────────────────────────────────────────────────────

function statusBadge(status: string) {
  const cls = status === 'draft' ? styles.badgeDraft
    : status === 'published' ? styles.badgePublished
    : styles.badgeArchived
  return <span className={`${styles.badge} ${cls}`}>{status}</span>
}

// ── Rule editor ───────────────────────────────────────────────────────────────

type RuleType = AnyRuleIn['type']

const RULE_TYPES: RuleType[] = [
  'required', 'min_length', 'max_length', 'regex',
  'min_value', 'max_value', 'min_items', 'max_items',
  'max_file_size', 'allowed_mime_types', 'required_in_language',
]

function makeDefaultRule(type: RuleType): AnyRuleIn {
  const common = { admin_label: '', applies_to_save: false }
  switch (type) {
    case 'required': return { ...common, type: 'required' }
    case 'min_length': return { ...common, type: 'min_length', min_length: 1 }
    case 'max_length': return { ...common, type: 'max_length', max_length: 100 }
    case 'regex': return { ...common, type: 'regex', pattern: '', failure_message: '' }
    case 'min_value': return { ...common, type: 'min_value', min_value: 0 }
    case 'max_value': return { ...common, type: 'max_value', max_value: 100 }
    case 'min_items': return { ...common, type: 'min_items', min_items: 1 }
    case 'max_items': return { ...common, type: 'max_items', max_items: 10 }
    case 'max_file_size': return { ...common, type: 'max_file_size', max_bytes: 10485760 }
    case 'allowed_mime_types': return { ...common, type: 'allowed_mime_types', mime_types: [] }
    case 'required_in_language': return { ...common, type: 'required_in_language', language: 'en' }
    default: return { ...common, type: 'required' }
  }
}

interface RuleEditorProps {
  rule: AnyRuleIn
  onChange: (r: AnyRuleIn) => void
  onRemove: () => void
}

function RuleEditor({ rule, onChange, onRemove }: RuleEditorProps) {
  const setR = (updates: Partial<AnyRuleIn>) => onChange({ ...rule, ...updates } as AnyRuleIn)

  function renderExtra() {
    switch (rule.type) {
      case 'min_length':
        return (
          <div className={styles.formGroup}>
            <label className={styles.label}>Min Length</label>
            <input className={styles.input} type="number" value={rule.min_length}
              onChange={e => setR({ min_length: parseInt(e.target.value) || 0 } as Partial<AnyRuleIn>)} />
          </div>
        )
      case 'max_length':
        return (
          <div className={styles.formGroup}>
            <label className={styles.label}>Max Length</label>
            <input className={styles.input} type="number" value={rule.max_length}
              onChange={e => setR({ max_length: parseInt(e.target.value) || 0 } as Partial<AnyRuleIn>)} />
          </div>
        )
      case 'regex':
        return (
          <>
            <div className={styles.formGroup}>
              <label className={styles.label}>Pattern</label>
              <input className={styles.input} value={rule.pattern}
                onChange={e => setR({ pattern: e.target.value } as Partial<AnyRuleIn>)} placeholder="^[A-Z]" />
            </div>
            <div className={styles.formGroup}>
              <label className={styles.label}>Failure Message</label>
              <input className={styles.input} value={rule.failure_message}
                onChange={e => setR({ failure_message: e.target.value } as Partial<AnyRuleIn>)} />
            </div>
          </>
        )
      case 'min_value':
        return (
          <div className={styles.formGroup}>
            <label className={styles.label}>Min Value</label>
            <input className={styles.input} type="number" value={rule.min_value}
              onChange={e => setR({ min_value: parseFloat(e.target.value) || 0 } as Partial<AnyRuleIn>)} />
          </div>
        )
      case 'max_value':
        return (
          <div className={styles.formGroup}>
            <label className={styles.label}>Max Value</label>
            <input className={styles.input} type="number" value={rule.max_value}
              onChange={e => setR({ max_value: parseFloat(e.target.value) || 0 } as Partial<AnyRuleIn>)} />
          </div>
        )
      case 'min_items':
        return (
          <div className={styles.formGroup}>
            <label className={styles.label}>Min Items</label>
            <input className={styles.input} type="number" value={rule.min_items}
              onChange={e => setR({ min_items: parseInt(e.target.value) || 0 } as Partial<AnyRuleIn>)} />
          </div>
        )
      case 'max_items':
        return (
          <div className={styles.formGroup}>
            <label className={styles.label}>Max Items</label>
            <input className={styles.input} type="number" value={rule.max_items}
              onChange={e => setR({ max_items: parseInt(e.target.value) || 0 } as Partial<AnyRuleIn>)} />
          </div>
        )
      case 'max_file_size':
        return (
          <div className={styles.formGroup}>
            <label className={styles.label}>Max Bytes</label>
            <input className={styles.input} type="number" value={rule.max_bytes}
              onChange={e => setR({ max_bytes: parseInt(e.target.value) || 0 } as Partial<AnyRuleIn>)} />
          </div>
        )
      case 'allowed_mime_types':
        return (
          <div className={styles.formGroup}>
            <label className={styles.label}>MIME Types (one per line)</label>
            <textarea className={styles.textarea} rows={3}
              value={rule.mime_types.join('\n')}
              onChange={e => setR({ mime_types: e.target.value.split('\n').map(s => s.trim()).filter(Boolean) } as Partial<AnyRuleIn>)} />
          </div>
        )
      case 'required_in_language':
        return (
          <div className={styles.formGroup}>
            <label className={styles.label}>Language Code</label>
            <input className={styles.input} value={rule.language}
              onChange={e => setR({ language: e.target.value } as Partial<AnyRuleIn>)} placeholder="en" />
          </div>
        )
      default:
        return null
    }
  }

  return (
    <div style={{ background: '#f8f8f8', border: '1px solid #e8e8e8', borderRadius: '4px', padding: '0.6rem 0.75rem', marginBottom: '0.4rem' }}>
      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'flex-start', flexWrap: 'wrap' }}>
        <div className={styles.formGroup} style={{ minWidth: '130px', flex: 'none' }}>
          <label className={styles.label}>Rule Type</label>
          <select className={styles.select} value={rule.type}
            onChange={e => onChange(makeDefaultRule(e.target.value as RuleType))}>
            {RULE_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <div className={styles.formGroup} style={{ minWidth: '150px' }}>
          <label className={styles.label}>Admin Label</label>
          <input className={styles.input} value={rule.admin_label}
            onChange={e => setR({ admin_label: e.target.value } as Partial<AnyRuleIn>)} placeholder="optional" />
        </div>
        <div className={styles.formGroup} style={{ flex: 'none' }}>
          <label className={styles.label}>On Save</label>
          <label className={styles.checkbox} style={{ padding: '0.45rem 0' }}>
            <input type="checkbox" checked={rule.applies_to_save}
              onChange={e => setR({ applies_to_save: e.target.checked } as Partial<AnyRuleIn>)} />
            applies_to_save
          </label>
        </div>
        {renderExtra()}
        <button type="button" className={`${styles.btn} ${styles.btnDanger}`}
          onClick={onRemove} style={{ alignSelf: 'flex-end' }}>
          ×
        </button>
      </div>
    </div>
  )
}

// ── Field Definition Editor ───────────────────────────────────────────────────

// ── Submodel version picker ───────────────────────────────────────────────────

interface SubmodelVersionPickerProps {
  value: string | null | undefined
  onChange: (versionId: string | null) => void
  allConfigs: FieldConfigOut[]
}

function SubmodelVersionPicker({ value, onChange, allConfigs }: SubmodelVersionPickerProps) {
  const [selectedConfigId, setSelectedConfigId] = useState<string>('')
  const [versions, setVersions] = useState<import('./apiUdm').ConfigVersionListItem[]>([])
  const [loadingVersions, setLoadingVersions] = useState(false)

  // When a config is chosen, load its versions
  useEffect(() => {
    if (!selectedConfigId) { setVersions([]); return }
    setLoadingVersions(true)
    import('./apiUdm').then(({ udmListConfigVersions }) =>
      udmListConfigVersions(selectedConfigId)
        .then(setVersions)
        .catch(() => setVersions([]))
        .finally(() => setLoadingVersions(false))
    )
  }, [selectedConfigId])

  // If we have a current value but no selectedConfigId, try to derive the config
  // by finding which config owns the version (via published/draft lookup — best effort)
  // — we just leave the picker blank and show the current ID as info text.

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
      <label className={styles.label}>Config (for submodel version)</label>
      <select className={styles.select} value={selectedConfigId}
        onChange={e => { setSelectedConfigId(e.target.value); onChange(null) }}>
        <option value="">— select config —</option>
        {allConfigs.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
      </select>

      {selectedConfigId && (
        <>
          <label className={styles.label}>Config Version *</label>
          {loadingVersions ? (
            <div style={{ fontSize: '0.82rem', color: '#888' }}>Loading versions…</div>
          ) : (
            <select className={styles.select} value={value ?? ''}
              onChange={e => onChange(e.target.value || null)}>
              <option value="">— select version —</option>
              {versions.map(v => (
                <option key={v.id} value={v.id}>
                  {v.status} {v.published_at ? `(published ${new Date(v.published_at).toLocaleDateString()})` : `(created ${new Date(v.created_at).toLocaleDateString()})`}
                </option>
              ))}
            </select>
          )}
        </>
      )}

      {value && (
        <div style={{ fontSize: '0.78rem', color: '#666' }}>
          Current version ID: <span className={styles.monoText}>{value}</span>
          {' '}<button type="button" style={{ fontSize: '0.78rem', color: '#dc2626', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
            onClick={() => onChange(null)}>clear</button>
        </div>
      )}
    </div>
  )
}

// ── Field Definition Editor ───────────────────────────────────────────────────

interface FieldEditorProps {
  field: FieldDefinitionIn
  onChange: (f: FieldDefinitionIn) => void
  onRemove: () => void
  languages: string[]
  allConfigs: FieldConfigOut[]
}

function FieldEditor({ field, onChange, onRemove, languages, allConfigs }: FieldEditorProps) {
  const [expanded, setExpanded] = useState(false)

  const setF = (updates: Partial<FieldDefinitionIn>) => onChange({ ...field, ...updates })
  const setLabel = (lang: string, val: string) =>
    setF({ labels: { ...field.labels, [lang]: val } })
  const setHelpText = (lang: string, val: string) =>
    setF({ help_texts: { ...(field.help_texts ?? {}), [lang]: val } })

  const rules = (field.rules ?? []) as AnyRuleIn[]

  function addRule() {
    setF({ rules: [...rules, makeDefaultRule('required')] })
  }

  function updateRule(i: number, r: AnyRuleIn) {
    setF({ rules: rules.map((x, j) => j === i ? r : x) })
  }

  function removeRule(i: number) {
    setF({ rules: rules.filter((_, j) => j !== i) })
  }

  const tc = field.type_config ?? {}

  return (
    <div className={styles.fieldCard}>
      <div className={styles.fieldCardHeader}>
        <span className={styles.fieldCardTitle}>
          {field.slug || <em style={{ color: '#999' }}>new field</em>}
          {' '}
          <span className={styles.badge} style={{ background: '#eee', color: '#555', fontSize: '0.75rem' }}>
            {field.data_type}
          </span>
          {rules.length > 0 && (
            <span className={styles.ruleTag}>{rules.length} rule{rules.length > 1 ? 's' : ''}</span>
          )}
        </span>
        <div className={styles.tableActions}>
          <button type="button" className={`${styles.btn} ${styles.btnSecondary}`}
            onClick={() => setExpanded(!expanded)}>
            {expanded ? 'Collapse' : 'Edit'}
          </button>
          <button type="button" className={`${styles.btn} ${styles.btnDanger}`} onClick={onRemove}>
            Remove
          </button>
        </div>
      </div>

      {expanded && (
        <>
          <div className={styles.fieldCardBody}>
            <div className={styles.formGroup}>
              <label className={styles.label}>Slug *</label>
              <input className={styles.input} value={field.slug}
                onChange={e => setF({ slug: e.target.value })} placeholder="field_slug" />
            </div>
            <div className={styles.formGroup}>
              <label className={styles.label}>Data Type *</label>
              <select className={styles.select} value={field.data_type}
                onChange={e => {
                  const dt = e.target.value as DataType
                  const isSubmodel = dt === 'submodel_select' || dt === 'submodel_list'
                  setF({
                    data_type: dt,
                    submodel_config_version_id: isSubmodel ? field.submodel_config_version_id : null,
                  })
                }}>
                {DATA_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div className={styles.formGroup}>
              <label className={styles.label}>Sort Order</label>
              <input className={styles.input} type="number" value={field.sort_order}
                onChange={e => setF({ sort_order: parseInt(e.target.value) || 0 })} />
            </div>
            <div className={styles.formGroup}>
              <label className={styles.label}>Flags</label>
              <label className={styles.checkbox}>
                <input type="checkbox" checked={field.is_localized}
                  onChange={e => setF({ is_localized: e.target.checked })} />
                Localized
              </label>
            </div>

            {languages.map(lang => (
              <div key={lang} className={styles.formGroup} style={{ minWidth: '200px' }}>
                <label className={styles.label}>Label [{lang}] *</label>
                <input className={styles.input} value={field.labels[lang] ?? ''}
                  onChange={e => setLabel(lang, e.target.value)}
                  placeholder={`Label in ${lang}`} />
                <label className={styles.label} style={{ marginTop: '0.25rem' }}>Help [{lang}]</label>
                <input className={styles.input} value={(field.help_texts ?? {})[lang] ?? ''}
                  onChange={e => setHelpText(lang, e.target.value)}
                  placeholder={`Help text in ${lang}`} />
              </div>
            ))}

            {/* Type config: choices for select */}
            {(field.data_type === 'select_single' || field.data_type === 'select_multi') && (
              <div className={styles.formGroup} style={{ gridColumn: '1 / -1' }}>
                <label className={styles.label}>Choices (one per line) *</label>
                <textarea className={styles.textarea} rows={3}
                  value={(tc['choices'] as string[] || []).join('\n')}
                  onChange={e => setF({
                    type_config: {
                      ...tc,
                      choices: e.target.value.split('\n').map(s => s.trim()).filter(Boolean),
                    },
                  })} />
              </div>
            )}

            {/* Type config: max_length for text_short */}
            {field.data_type === 'text_short' && (
              <div className={styles.formGroup}>
                <label className={styles.label}>Max Length (type_config)</label>
                <input className={styles.input} type="number"
                  value={(tc['max_length'] as number) ?? ''}
                  onChange={e => setF({
                    type_config: { ...tc, max_length: parseInt(e.target.value) || undefined },
                  })} />
              </div>
            )}

            {/* Type config: number bounds for integer/float */}
            {(field.data_type === 'integer' || field.data_type === 'float') && (
              <>
                <div className={styles.formGroup}>
                  <label className={styles.label}>Min (type_config)</label>
                  <input className={styles.input} type="number"
                    value={(tc['min'] as number) ?? ''}
                    onChange={e => setF({ type_config: { ...tc, min: e.target.value ? parseFloat(e.target.value) : undefined } })} />
                </div>
                <div className={styles.formGroup}>
                  <label className={styles.label}>Max (type_config)</label>
                  <input className={styles.input} type="number"
                    value={(tc['max'] as number) ?? ''}
                    onChange={e => setF({ type_config: { ...tc, max: e.target.value ? parseFloat(e.target.value) : undefined } })} />
                </div>
                {field.data_type === 'float' && (
                  <div className={styles.formGroup}>
                    <label className={styles.label}>Decimal Places</label>
                    <input className={styles.input} type="number"
                      value={(tc['decimal_places'] as number) ?? ''}
                      onChange={e => setF({ type_config: { ...tc, decimal_places: parseInt(e.target.value) || undefined } })} />
                  </div>
                )}
              </>
            )}

            {/* Type config: group/user restrictions */}
            {(field.data_type === 'user_select' || field.data_type === 'user_select_multi') && (
              <div className={styles.formGroup} style={{ gridColumn: '1 / -1' }}>
                <label className={styles.label}>Limit to Group IDs (comma-separated, optional)</label>
                <input className={styles.input}
                  value={((tc['limit_to_group_ids'] as number[]) ?? []).join(', ')}
                  onChange={e => setF({
                    type_config: {
                      ...tc,
                      limit_to_group_ids: e.target.value
                        ? e.target.value.split(',').map(s => parseInt(s.trim())).filter(n => !isNaN(n))
                        : undefined,
                    },
                  })}
                  placeholder="3, 7 (leave blank for all users)" />
              </div>
            )}

            {(field.data_type === 'entity_select' || field.data_type === 'entity_select_multi') && (
              <div className={styles.formGroup} style={{ gridColumn: '1 / -1' }}>
                <label className={styles.label}>Limit to Type IDs (comma-separated, optional)</label>
                <input className={styles.input}
                  value={((tc['limit_to_type_ids'] as string[]) ?? []).join(', ')}
                  onChange={e => setF({
                    type_config: {
                      ...tc,
                      limit_to_type_ids: e.target.value
                        ? e.target.value.split(',').map(s => s.trim()).filter(Boolean)
                        : undefined,
                    },
                  })}
                  placeholder="uuid1, uuid2 (leave blank for any type)" />
              </div>
            )}

            {/* Submodel config version — required for submodel_select / submodel_list */}
            {(field.data_type === 'submodel_select' || field.data_type === 'submodel_list') && (
              <div className={styles.formGroup} style={{ gridColumn: '1 / -1' }}>
                <SubmodelVersionPicker
                  value={field.submodel_config_version_id ?? null}
                  onChange={versionId => setF({ submodel_config_version_id: versionId })}
                  allConfigs={allConfigs}
                />
              </div>
            )}
          </div>

          {/* Rules */}
          <div className={styles.subsection}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
              <span className={styles.subsectionTitle}>Validation Rules ({rules.length})</span>
              <button type="button" className={`${styles.btn} ${styles.btnSecondary}`}
                onClick={addRule} style={{ fontSize: '0.8rem', padding: '0.25rem 0.6rem' }}>
                + Add Rule
              </button>
            </div>
            {rules.length === 0 && (
              <div style={{ fontSize: '0.85rem', color: '#999', fontStyle: 'italic' }}>No rules. Add rules to validate field values on save or transition.</div>
            )}
            {rules.map((r, i) => (
              <RuleEditor key={i} rule={r} onChange={updated => updateRule(i, updated)} onRemove={() => removeRule(i)} />
            ))}
          </div>
        </>
      )}
    </div>
  )
}

// ── Draft Editor ──────────────────────────────────────────────────────────────

interface DraftEditorProps {
  configId: string
  languages: string[]
  onSaved: (v: ConfigVersionOut) => void
  allConfigs: FieldConfigOut[]
}

function DraftEditor({ configId, languages, onSaved, allConfigs }: DraftEditorProps) {
  const [draft, setDraft] = useState<ConfigVersionOut | null>(null)
  const [notes, setNotes] = useState('')
  const [fields, setFields] = useState<FieldDefinitionIn[]>([])
  const [saving, setSaving] = useState(false)
  const [publishing, setPublishing] = useState(false)
  const [errors, setErrors] = useState<string[]>([])
  const [success, setSuccess] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const v = await udmGetDraftVersion(configId)
      setDraft(v)
      setNotes(v.notes)
      setFields(v.fields.map(fdToIn))
    } catch {
      setDraft(null)
      setFields([])
    }
  }, [configId])

  useEffect(() => { void load() }, [load])

  function fdToIn(fd: FieldDefinitionOut): FieldDefinitionIn {
    return {
      slug: fd.slug,
      data_type: fd.data_type as DataType,
      sort_order: fd.sort_order,
      is_localized: fd.is_localized,
      labels: fd.label as Record<string, string>,
      help_texts: fd.help_text as Record<string, string>,
      type_config: fd.type_config as Record<string, unknown>,
      submodel_config_version_id: fd.submodel_config?.version_id ?? null,
      rules: [],
    }
  }

  function addField() {
    const labels: Record<string, string> = {}
    languages.forEach(l => { labels[l] = '' })
    setFields(prev => [...prev, {
      slug: '',
      data_type: 'text_short',
      sort_order: prev.length,
      is_localized: false,
      labels,
      type_config: {},
      rules: [],
    }])
  }

  async function handleSave() {
    setSaving(true)
    setErrors([])
    setSuccess(null)
    try {
      const v = await udmReplaceDraft(configId, { notes, fields, multi_field_rules: [] })
      setDraft(v)
      setSuccess('Draft saved.')
      onSaved(v)
    } catch (e) {
      setErrors(e instanceof UdmApiError ? e.allMessages : [e instanceof Error ? e.message : 'Save failed'])
    } finally {
      setSaving(false)
    }
  }

  async function handlePublish() {
    setPublishing(true)
    setErrors([])
    setSuccess(null)
    try {
      const v = await udmPublishDraft(configId)
      setDraft(v)
      setSuccess('Published successfully.')
      onSaved(v)
    } catch (e) {
      setErrors(e instanceof UdmApiError ? e.allMessages : [e instanceof Error ? e.message : 'Publish failed'])
    } finally {
      setPublishing(false)
    }
  }

  return (
    <div>
      <div className={styles.subsectionTitle}>Draft Version</div>
      {draft ? (
        <div>
          <div className={styles.row}>
            <div className={styles.formGroup} style={{ flex: 2 }}>
              <label className={styles.label}>Change Notes</label>
              <input className={styles.input} value={notes}
                onChange={e => setNotes(e.target.value)} placeholder="Notes for this version" />
            </div>
          </div>

          <div style={{ marginTop: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
              <span className={styles.subsectionTitle}>Fields ({fields.length})</span>
              <button type="button" className={`${styles.btn} ${styles.btnSecondary}`} onClick={addField}>
                + Add Field
              </button>
            </div>
            {fields.length === 0 && <div className={styles.emptyState}>No fields yet. Add a field to get started.</div>}
            {fields.map((f, i) => (
              <FieldEditor
                key={i}
                field={f}
                languages={languages}
                allConfigs={allConfigs}
                onChange={updated => setFields(prev => prev.map((x, j) => j === i ? updated : x))}
                onRemove={() => setFields(prev => prev.filter((_, j) => j !== i))}
              />
            ))}
          </div>

          {errors.length > 0 && (
            <div className={styles.error}>
              {errors.map((msg, i) => <div key={i}>{msg}</div>)}
            </div>
          )}
          {success && <div className={styles.success}>{success}</div>}

          <div className={styles.row} style={{ marginTop: '1rem' }}>
            <button type="button" className={`${styles.btn} ${styles.btnPrimary}`}
              onClick={handleSave} disabled={saving}>
              {saving ? 'Saving…' : 'Save Draft'}
            </button>
            <button type="button" className={`${styles.btn} ${styles.btnSuccess}`}
              onClick={handlePublish} disabled={publishing}>
              {publishing ? 'Publishing…' : 'Publish Draft'}
            </button>
          </div>
        </div>
      ) : (
        <div className={styles.emptyState}>No draft version exists.</div>
      )}
    </div>
  )
}

// ── Config Detail ─────────────────────────────────────────────────────────────

interface ConfigDetailProps {
  configId: string
  onBack: () => void
}

function ConfigDetail({ configId, onBack }: ConfigDetailProps) {
  const [config, setConfig] = useState<FieldConfigOut | null>(null)
  const [published, setPublished] = useState<ConfigVersionOut | null>(null)
  const [allTypes, setAllTypes] = useState<UDMTypeOut[]>([])
  const [allConfigs, setAllConfigs] = useState<FieldConfigOut[]>([])
  const [editName, setEditName] = useState('')
  const [editDesc, setEditDesc] = useState('')
  const [editingMeta, setEditingMeta] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [assignTypeId, setAssignTypeId] = useState('')
  const [assigningType, setAssigningType] = useState(false)

  const load = useCallback(async () => {
    try {
      const cfg = await fetch(`/api/udm/configs/${configId}/`, { credentials: 'include' })
        .then(r => r.json() as Promise<FieldConfigOut>)
      setConfig(cfg)
      setEditName(cfg.name)
      setEditDesc(cfg.description)
    } catch { /* ignore */ }

    try {
      const pub = await udmGetPublishedVersion(configId)
      setPublished(pub)
    } catch { setPublished(null) }

    try {
      const types = await udmListTypes()
      setAllTypes(types)
    } catch { /* ignore */ }

    try {
      const cfgs = await udmListConfigs()
      setAllConfigs(cfgs)
    } catch { /* ignore */ }
  }, [configId])

  useEffect(() => { void load() }, [load])

  async function handleSaveMeta() {
    setSaving(true)
    setError(null)
    setSuccess(null)
    try {
      const c = await udmUpdateConfig(configId, { name: editName, description: editDesc })
      setConfig(c)
      setEditingMeta(false)
      setSuccess('Config updated.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Update failed')
    } finally {
      setSaving(false)
    }
  }

  async function handleAssignType() {
    if (!assignTypeId) return
    setAssigningType(true)
    setError(null)
    try {
      const typeName = allTypes.find(t => t.id === assignTypeId)?.name ?? assignTypeId
      await udmUpdateType(assignTypeId, configId)
      setSuccess(`Config assigned to type "${typeName}"`)
      setAssignTypeId('')
      void load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Assign failed')
    } finally {
      setAssigningType(false)
    }
  }

  if (!config) return <div className={styles.emptyState}>Loading…</div>

  const languages = config.languages.map(l => l.code)

  return (
    <div>
      <div className={styles.detailHeader}>
        <button type="button" className={styles.backBtn} onClick={onBack}>← Back to Configs</button>
        <h2 className={styles.pageTitle} style={{ margin: 0 }}>{config.name}</h2>
      </div>

      {/* Meta */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>Config Info</div>
        {editingMeta ? (
          <>
            <div className={styles.row}>
              <div className={styles.formGroup}>
                <label className={styles.label}>Name *</label>
                <input className={styles.input} value={editName} onChange={e => setEditName(e.target.value)} />
              </div>
              <div className={styles.formGroup} style={{ flex: 2 }}>
                <label className={styles.label}>Description</label>
                <input className={styles.input} value={editDesc} onChange={e => setEditDesc(e.target.value)} />
              </div>
            </div>
            {error && <div className={styles.error}>{error}</div>}
            {success && <div className={styles.success}>{success}</div>}
            <div className={styles.row} style={{ marginTop: '0.75rem' }}>
              <button type="button" className={`${styles.btn} ${styles.btnPrimary}`}
                onClick={handleSaveMeta} disabled={saving}>
                {saving ? 'Saving…' : 'Save'}
              </button>
              <button type="button" className={`${styles.btn} ${styles.btnSecondary}`}
                onClick={() => setEditingMeta(false)}>Cancel</button>
            </div>
          </>
        ) : (
          <div className={styles.row}>
            <div>
              <div><strong>Name:</strong> {config.name}</div>
              {config.description && <div><strong>Description:</strong> {config.description}</div>}
              <div style={{ marginTop: '0.5rem' }}>
                <strong>Languages:</strong>{' '}
                <span className={styles.langGrid}>
                  {config.languages.map(l => (
                    <span key={l.code} className={`${styles.langTag} ${l.is_default ? styles.langTagDefault : ''}`}>
                      {l.code}{l.is_default ? ' (default)' : ''}
                    </span>
                  ))}
                </span>
              </div>
              <div style={{ marginTop: '0.5rem' }}>
                <strong>Stale entities:</strong> {config.stale_entity_count}
              </div>
              {config.type_ids.length > 0 && (
                <div style={{ marginTop: '0.5rem' }}>
                  <strong>Used by types:</strong> {config.type_ids.map(id => (
                    <span key={id} className={styles.monoText} style={{ marginLeft: '0.5rem', fontSize: '0.8rem' }}>{id}</span>
                  ))}
                </div>
              )}
            </div>
            <button type="button" className={`${styles.btn} ${styles.btnSecondary}`}
              onClick={() => setEditingMeta(true)} style={{ alignSelf: 'flex-start' }}>
              Edit
            </button>
          </div>
        )}

        <div className={styles.subsection}>
          <div className={styles.subsectionTitle}>Assign to UDM Type</div>
          {allTypes.length === 0 ? (
            <div className={styles.info}>No UDM types available. Create types in the Types tab first.</div>
          ) : (
            <div className={styles.row}>
              <div className={styles.formGroup}>
                <label className={styles.label}>Type</label>
                <select className={styles.select} value={assignTypeId} onChange={e => setAssignTypeId(e.target.value)}>
                  <option value="">— select type —</option>
                  {allTypes
                    .filter(t => !config?.type_ids.includes(t.id))
                    .map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
              </div>
              <button type="button" className={`${styles.btn} ${styles.btnSecondary}`}
                onClick={handleAssignType} disabled={assigningType || !assignTypeId}
                style={{ alignSelf: 'flex-end' }}>
                {assigningType ? 'Assigning…' : 'Assign'}
              </button>
            </div>
          )}
          {error && !editingMeta && <div className={styles.error}>{error}</div>}
          {success && !editingMeta && <div className={styles.success}>{success}</div>}
        </div>
      </div>

      {/* Published version summary */}
      {published && (
        <div className={styles.section}>
          <div className={styles.sectionTitle}>
            Published Version {statusBadge('published')}
            {published.published_at && (
              <span className={styles.info} style={{ marginLeft: '0.5rem', fontSize: '0.85rem' }}>
                — {new Date(published.published_at).toLocaleString()}
              </span>
            )}
          </div>
          <div><strong>Fields:</strong> {published.fields.length}</div>
          {published.workflow && (
            <div><strong>Workflow:</strong> {published.workflow.states.length} states, {published.workflow.transitions.length} transitions</div>
          )}
          <div style={{ marginTop: '0.5rem' }}>
            {published.fields.map(f => (
              <span key={f.slug} className={styles.ruleTag}>{f.slug} ({f.data_type})</span>
            ))}
          </div>
        </div>
      )}

      {/* Draft editor */}
      <div className={styles.section}>
        <DraftEditor
          configId={configId}
          languages={languages}
          allConfigs={allConfigs}
          onSaved={() => void load()}
        />
      </div>
    </div>
  )
}

// ── Configs Tab ───────────────────────────────────────────────────────────────

function ConfigsTab() {
  const [configs, setConfigs] = useState<FieldConfigOut[]>([])
  const [loading, setLoading] = useState(true)
  const [view, setView] = useState<ConfigView>('list')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [newLangs, setNewLangs] = useState('en')
  const [createError, setCreateError] = useState<string | null>(null)

  const loadConfigs = useCallback(async () => {
    setLoading(true)
    try {
      const list = await udmListConfigs()
      setConfigs(list)
    } catch { /* ignore */ }
    setLoading(false)
  }, [])

  useEffect(() => { void loadConfigs() }, [loadConfigs])

  async function handleCreate() {
    setCreateError(null)
    const codes = newLangs.split(',').map(s => s.trim()).filter(Boolean)
    if (!newName.trim() || codes.length === 0) {
      setCreateError('Name and at least one language code are required.')
      return
    }
    try {
      const languages = codes.map((code, i) => ({
        code, label: code.toUpperCase(), is_default: i === 0, sort_order: i,
      }))
      await udmCreateConfig({ name: newName, description: newDesc, languages })
      setNewName('')
      setNewDesc('')
      setNewLangs('en')
      setCreating(false)
      void loadConfigs()
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : 'Create failed')
    }
  }

  async function handleDelete(id: string, name: string) {
    if (!confirm(`Delete config "${name}"? This cannot be undone.`)) return
    try {
      await udmDeleteConfig(id)
      void loadConfigs()
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Delete failed')
    }
  }

  if (view === 'detail' && selectedId) {
    return (
      <ConfigDetail
        configId={selectedId}
        onBack={() => { setView('list'); void loadConfigs() }}
      />
    )
  }

  return (
    <div>
      <div className={styles.row} style={{ marginBottom: '1rem', justifyContent: 'flex-end' }}>
        <button type="button" className={`${styles.btn} ${styles.btnPrimary}`}
          onClick={() => setCreating(!creating)}>
          {creating ? 'Cancel' : '+ New Field Config'}
        </button>
      </div>

      {creating && (
        <div className={styles.section}>
          <div className={styles.sectionTitle}>Create Field Config</div>
          <div className={styles.row}>
            <div className={styles.formGroup}>
              <label className={styles.label}>Name *</label>
              <input className={styles.input} value={newName} onChange={e => setNewName(e.target.value)}
                placeholder="Standard Workshop Form" />
            </div>
            <div className={styles.formGroup} style={{ flex: 2 }}>
              <label className={styles.label}>Description</label>
              <input className={styles.input} value={newDesc} onChange={e => setNewDesc(e.target.value)} />
            </div>
            <div className={styles.formGroup}>
              <label className={styles.label}>Language codes (comma-separated) *</label>
              <input className={styles.input} value={newLangs} onChange={e => setNewLangs(e.target.value)}
                placeholder="en, de" />
            </div>
          </div>
          {createError && <div className={styles.error}>{createError}</div>}
          <div className={styles.row} style={{ marginTop: '0.75rem' }}>
            <button type="button" className={`${styles.btn} ${styles.btnPrimary}`} onClick={handleCreate}>
              Create
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <div className={styles.emptyState}>Loading…</div>
      ) : configs.length === 0 ? (
        <div className={styles.emptyState}>No field configs yet.</div>
      ) : (
        <div className={styles.section}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Name</th>
                <th>Languages</th>
                <th>Stale Entities</th>
                <th>Used by Types</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {configs.map(cfg => (
                <tr key={cfg.id}>
                  <td><strong>{cfg.name}</strong></td>
                  <td>
                    <span className={styles.langGrid}>
                      {cfg.languages.map(l => (
                        <span key={l.code} className={`${styles.langTag} ${l.is_default ? styles.langTagDefault : ''}`}>
                          {l.code}
                        </span>
                      ))}
                    </span>
                  </td>
                  <td>{cfg.stale_entity_count}</td>
                  <td>{cfg.type_ids.length}</td>
                  <td>
                    <div className={styles.tableActions}>
                      <button type="button" className={`${styles.btn} ${styles.btnSecondary}`}
                        onClick={() => { setSelectedId(cfg.id); setView('detail') }}>
                        Open
                      </button>
                      <button type="button" className={`${styles.btn} ${styles.btnDanger}`}
                        onClick={() => void handleDelete(cfg.id, cfg.name)}>
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ── Policies Tab ──────────────────────────────────────────────────────────────

function PoliciesTab() {
  const [policies, setPolicies] = useState<PolicyOut[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [editSlug, setEditSlug] = useState<string | null>(null)
  const [newSlug, setNewSlug] = useState('')
  const [source, setSource] = useState('')
  const [editSource, setEditSource] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const loadPolicies = useCallback(async () => {
    setLoading(true)
    try {
      const list = await udmListPolicies()
      setPolicies(list)
    } catch { /* ignore */ }
    setLoading(false)
  }, [])

  useEffect(() => { void loadPolicies() }, [loadPolicies])

  async function handleCreate() {
    setError(null)
    if (!newSlug.trim() || !source.trim()) {
      setError('Slug and source are required.')
      return
    }
    try {
      await udmCreatePolicy({ slug: newSlug.trim(), source })
      setNewSlug('')
      setSource('')
      setCreating(false)
      setSuccess('Policy created.')
      void loadPolicies()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Create failed')
    }
  }

  async function handleUpdate(slug: string) {
    setError(null)
    try {
      await udmUpdatePolicy(slug, { source: editSource })
      setEditSlug(null)
      setSuccess('Policy updated.')
      void loadPolicies()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Update failed')
    }
  }

  async function handleDelete(slug: string) {
    if (!confirm(`Delete policy "${slug}"?`)) return
    try {
      await udmDeletePolicy(slug)
      void loadPolicies()
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Delete failed')
    }
  }

  return (
    <div>
      <div className={styles.row} style={{ marginBottom: '1rem', justifyContent: 'flex-end' }}>
        <button type="button" className={`${styles.btn} ${styles.btnPrimary}`}
          onClick={() => setCreating(!creating)}>
          {creating ? 'Cancel' : '+ New Policy'}
        </button>
      </div>

      {creating && (
        <div className={styles.section}>
          <div className={styles.sectionTitle}>Create Rego Policy</div>
          <div className={styles.formGroup}>
            <label className={styles.label}>Slug *</label>
            <input className={styles.input} value={newSlug} onChange={e => setNewSlug(e.target.value)}
              placeholder="staff_full_access" />
          </div>
          <div className={styles.formGroup} style={{ marginTop: '0.5rem' }}>
            <label className={styles.label}>Rego Source *</label>
            <textarea className={styles.textarea} rows={8} value={source}
              onChange={e => setSource(e.target.value)}
              placeholder={'package udm\n\ndefault allow := false\n\nallow {\n  input.user.is_staff\n}'} />
          </div>
          {error && <div className={styles.error}>{error}</div>}
          {success && <div className={styles.success}>{success}</div>}
          <div className={styles.row} style={{ marginTop: '0.75rem' }}>
            <button type="button" className={`${styles.btn} ${styles.btnPrimary}`} onClick={handleCreate}>
              Create
            </button>
          </div>
        </div>
      )}

      {!loading && success && !creating && <div className={styles.success} style={{ marginBottom: '0.5rem' }}>{success}</div>}

      {loading ? (
        <div className={styles.emptyState}>Loading…</div>
      ) : policies.length === 0 ? (
        <div className={styles.emptyState}>No policies yet.</div>
      ) : (
        policies.map(policy => (
          <div key={policy.slug} className={styles.section}>
            <div className={styles.fieldCardHeader}>
              <span className={styles.monoText} style={{ fontWeight: 600 }}>{policy.slug}</span>
              <div className={styles.tableActions}>
                {editSlug === policy.slug ? (
                  <>
                    <button type="button" className={`${styles.btn} ${styles.btnPrimary}`}
                      onClick={() => void handleUpdate(policy.slug)}>Save</button>
                    <button type="button" className={`${styles.btn} ${styles.btnSecondary}`}
                      onClick={() => setEditSlug(null)}>Cancel</button>
                  </>
                ) : (
                  <>
                    <button type="button" className={`${styles.btn} ${styles.btnSecondary}`}
                      onClick={() => { setEditSlug(policy.slug); setEditSource(policy.source) }}>Edit</button>
                    <button type="button" className={`${styles.btn} ${styles.btnDanger}`}
                      onClick={() => void handleDelete(policy.slug)}>Delete</button>
                  </>
                )}
              </div>
            </div>
            {editSlug === policy.slug ? (
              <>
                <textarea className={styles.textarea} rows={10} value={editSource}
                  onChange={e => setEditSource(e.target.value)} style={{ width: '100%' }} />
                {error && <div className={styles.error}>{error}</div>}
              </>
            ) : (
              <pre className={styles.monoText} style={{ margin: 0, overflow: 'auto', maxHeight: '200px', padding: '0.5rem', background: '#f8f8f8', borderRadius: '4px', fontSize: '0.8rem' }}>
                {policy.source}
              </pre>
            )}
          </div>
        ))
      )}
    </div>
  )
}

// ── Policy Evaluator ──────────────────────────────────────────────────────────

const ACTIONS = ['view', 'save', 'transition', 'delete']

interface PolicyEvaluatorProps {
  typeId: string
}

function PolicyEvaluator({ typeId }: PolicyEvaluatorProps) {
  const [entities, setEntities] = useState<EntityAutocompleteItem[]>([])
  const [users, setUsers] = useState<UserAutocompleteItem[]>([])
  const [entityId, setEntityId] = useState('')
  const [userId, setUserId] = useState('')
  const [action, setAction] = useState('view')
  const [transitionName, setTransitionName] = useState('')
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<PolicyEvalOut | null>(null)
  const [evalError, setEvalError] = useState<string | null>(null)
  const [activeResultTab, setActiveResultTab] = useState<'output' | 'input' | 'policies'>('output')

  useEffect(() => {
    udmSearchEntities('', typeId).then(setEntities).catch(() => {})
    udmSearchUsers('').then(setUsers).catch(() => {})
  }, [typeId])

  async function handleRun() {
    if (!entityId || !userId) return
    setRunning(true)
    setResult(null)
    setEvalError(null)
    try {
      const out = await udmEvalPolicy(
        typeId, entityId, userId, action,
        action === 'transition' && transitionName ? transitionName : undefined,
      )
      setResult(out)
    } catch (e) {
      setEvalError(e instanceof Error ? e.message : 'Evaluation failed')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div>
      {/* Controls */}
      <div className={styles.row} style={{ flexWrap: 'wrap', gap: '0.75rem', marginBottom: '0.75rem' }}>
        <div className={styles.formGroup} style={{ minWidth: '200px' }}>
          <label className={styles.label}>Entity</label>
          <select className={styles.select} value={entityId} onChange={e => setEntityId(e.target.value)}>
            <option value="">— select entity —</option>
            {entities.map(e => (
              <option key={e.id} value={e.id}>
                {e.display && e.display !== e.id ? `${e.display} (${e.id.slice(0, 8)}…)` : e.id}
              </option>
            ))}
          </select>
        </div>

        <div className={styles.formGroup} style={{ minWidth: '180px' }}>
          <label className={styles.label}>User</label>
          <select className={styles.select} value={userId} onChange={e => setUserId(e.target.value)}>
            <option value="">— select user —</option>
            {users.map(u => <option key={u.id} value={u.id}>{u.display_name}</option>)}
          </select>
        </div>

        <div className={styles.formGroup} style={{ minWidth: '130px', flex: 'none' }}>
          <label className={styles.label}>Action</label>
          <select className={styles.select} value={action} onChange={e => setAction(e.target.value)}>
            {ACTIONS.map(a => <option key={a} value={a}>{a}</option>)}
          </select>
        </div>

        {action === 'transition' && (
          <div className={styles.formGroup} style={{ minWidth: '140px' }}>
            <label className={styles.label}>Transition name</label>
            <input className={styles.input} value={transitionName}
              onChange={e => setTransitionName(e.target.value)} placeholder="submit" />
          </div>
        )}

        <button
          type="button"
          className={`${styles.btn} ${styles.btnPrimary}`}
          style={{ alignSelf: 'flex-end' }}
          onClick={handleRun}
          disabled={running || !entityId || !userId}
        >
          {running ? 'Evaluating…' : 'Evaluate'}
        </button>
      </div>

      {evalError && <div className={styles.error}>{evalError}</div>}

      {result && (
        <div>
          {/* Quick verdict */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: '0.75rem',
            marginBottom: '0.75rem', padding: '0.6rem 0.9rem',
            background: result.error ? '#fff3cd' : result.output.allow ? '#d4edda' : '#f8d7da',
            borderRadius: '6px',
            border: `1px solid ${result.error ? '#ffc107' : result.output.allow ? '#c3e6cb' : '#f5c6cb'}`,
          }}>
            <span style={{ fontWeight: 700, fontSize: '1rem' }}>
              {result.error ? '⚠ Error' : result.output.allow ? '✓ Allow' : '✗ Deny'}
            </span>
            {result.error && (
              <span style={{ fontSize: '0.875rem', color: '#856404' }}>{result.error}</span>
            )}
            {!result.error && (
              <span style={{ fontSize: '0.875rem', color: '#555' }}>
                {(result.output.messages as unknown[]).length} message{(result.output.messages as unknown[]).length !== 1 ? 's' : ''}
                {' · '}
                {(result.output.viewable_fields as string[]).length} viewable fields
                {' · '}
                {(result.output.editable_fields as string[]).length} editable fields
              </span>
            )}
          </div>

          {/* Messages */}
          {(result.output.messages as unknown[]).length > 0 && (
            <div style={{ marginBottom: '0.75rem' }}>
              {(result.output.messages as Array<string | Record<string, unknown>>).map((m, i) => {
                const level = typeof m === 'object' && m !== null ? String(m['level'] ?? '') : ''
                const text = typeof m === 'string' ? m : JSON.stringify(m)
                const color = level === 'critical' || level === 'error' ? '#dc2626'
                  : level === 'warning' ? '#d97706' : '#0066cc'
                return (
                  <div key={i} style={{ fontSize: '0.85rem', color, marginBottom: '0.2rem' }}>
                    {level && <strong>[{level}] </strong>}{text}
                  </div>
                )
              })}
            </div>
          )}

          {/* Field lists */}
          {((result.output.viewable_fields as string[]).length > 0 || (result.output.editable_fields as string[]).length > 0) && (
            <div style={{ display: 'flex', gap: '1.5rem', marginBottom: '0.75rem', flexWrap: 'wrap' }}>
              {(result.output.viewable_fields as string[]).length > 0 && (
                <div>
                  <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#555', marginBottom: '0.25rem' }}>Viewable fields</div>
                  <div className={styles.langGrid}>
                    {(result.output.viewable_fields as string[]).map(f => (
                      <span key={f} className={styles.ruleTag}>{f}</span>
                    ))}
                  </div>
                </div>
              )}
              {(result.output.editable_fields as string[]).length > 0 && (
                <div>
                  <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#555', marginBottom: '0.25rem' }}>Editable fields</div>
                  <div className={styles.langGrid}>
                    {(result.output.editable_fields as string[]).map(f => (
                      <span key={f} className={styles.ruleTag} style={{ background: '#d4edda', color: '#155724' }}>{f}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Detail tabs */}
          <div className={styles.tabs} style={{ marginBottom: '0.5rem' }}>
            {(['output', 'input', 'policies'] as const).map(tab => (
              <button key={tab} type="button"
                className={`${styles.tab} ${activeResultTab === tab ? styles.tabActive : ''}`}
                onClick={() => setActiveResultTab(tab)}>
                {tab === 'output' ? 'Full Output' : tab === 'input' ? 'Input Document' : `Policies (${result.policies.length})`}
              </button>
            ))}
          </div>

          {activeResultTab === 'output' && (
            <pre className={styles.monoText} style={{ margin: 0, padding: '0.75rem', background: '#f8f8f8', borderRadius: '6px', overflow: 'auto', maxHeight: '400px', fontSize: '0.8rem', border: '1px solid #e0e0e0' }}>
              {JSON.stringify(result.output, null, 2)}
            </pre>
          )}

          {activeResultTab === 'input' && (
            <pre className={styles.monoText} style={{ margin: 0, padding: '0.75rem', background: '#f8f8f8', borderRadius: '6px', overflow: 'auto', maxHeight: '400px', fontSize: '0.8rem', border: '1px solid #e0e0e0' }}>
              {JSON.stringify(result.input_document, null, 2)}
            </pre>
          )}

          {activeResultTab === 'policies' && (
            <div>
              {result.policies.length === 0 ? (
                <div className={styles.emptyState}>No policies assigned to this type.</div>
              ) : result.policies.map((p: Record<string, string>) => (
                <div key={p['slug']} style={{ marginBottom: '0.75rem' }}>
                  <div className={styles.monoText} style={{ fontWeight: 600, marginBottom: '0.25rem' }}>{p['slug']}</div>
                  <pre className={styles.monoText} style={{ margin: 0, padding: '0.75rem', background: '#f8f8f8', borderRadius: '6px', overflow: 'auto', maxHeight: '300px', fontSize: '0.8rem', border: '1px solid #e0e0e0' }}>
                    {p['source']}
                  </pre>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Types Tab ─────────────────────────────────────────────────────────────────

interface TypeDetailProps {
  udmType: UDMTypeOut
  onBack: () => void
  allConfigs: FieldConfigOut[]
  allPolicies: PolicyOut[]
  onUpdated: (t: UDMTypeOut) => void
  isSuperuser: boolean
}

function TypeDetail({ udmType, onBack, allConfigs, allPolicies, onUpdated, isSuperuser }: TypeDetailProps) {
  const [policies, setPolicies] = useState<PolicyOut[]>([])
  const [assignSlug, setAssignSlug] = useState('')
  const [configId, setConfigId] = useState(udmType.field_config_id ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const loadPolicies = useCallback(async () => {
    try {
      const list = await udmListTypePolicies(udmType.id)
      setPolicies(list)
    } catch { /* ignore */ }
  }, [udmType.id])

  useEffect(() => { void loadPolicies() }, [loadPolicies])

  async function handleAssignConfig() {
    setSaving(true)
    setError(null)
    setSuccess(null)
    try {
      const updated = await udmUpdateType(udmType.id, configId || null)
      onUpdated(updated)
      setSuccess('Config assigned.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Assign failed')
    } finally {
      setSaving(false)
    }
  }

  async function handleAssignPolicy() {
    if (!assignSlug) return
    setSaving(true)
    setError(null)
    try {
      await udmAssignPolicy(udmType.id, { policy_slug: assignSlug, sort_order: policies.length })
      setAssignSlug('')
      setSuccess('Policy assigned.')
      void loadPolicies()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Assign failed')
    } finally {
      setSaving(false)
    }
  }

  async function handleRemovePolicy(slug: string) {
    try {
      await udmRemovePolicy(udmType.id, slug)
      void loadPolicies()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Remove failed')
    }
  }

  return (
    <div>
      <div className={styles.detailHeader}>
        <button type="button" className={styles.backBtn} onClick={onBack}>← Back to Types</button>
        <h2 className={styles.pageTitle} style={{ margin: 0 }}>{udmType.name}</h2>
      </div>

      <div className={styles.section}>
        <div className={styles.sectionTitle}>Field Config Assignment</div>
        <div className={styles.row}>
          <div className={styles.formGroup}>
            <label className={styles.label}>Current Config</label>
            <div style={{ fontSize: '0.875rem', color: '#555', padding: '0.45rem 0' }}>
              {udmType.field_config_id
                ? (allConfigs.find(c => c.id === udmType.field_config_id)?.name ?? udmType.field_config_id)
                : 'None assigned'}
            </div>
          </div>
          <div className={styles.formGroup}>
            <label className={styles.label}>Assign Config</label>
            <select className={styles.select} value={configId} onChange={e => setConfigId(e.target.value)}>
              <option value="">— no config —</option>
              {allConfigs.map(c => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </div>
          <button type="button" className={`${styles.btn} ${styles.btnPrimary}`}
            onClick={handleAssignConfig} disabled={saving} style={{ alignSelf: 'flex-end' }}>
            {saving ? 'Saving…' : 'Apply'}
          </button>
        </div>
        {error && <div className={styles.error}>{error}</div>}
        {success && <div className={styles.success}>{success}</div>}
      </div>

      <div className={styles.section}>
        <div className={styles.sectionTitle}>Assigned Policies</div>
        {policies.length === 0 ? (
          <div className={styles.emptyState}>No policies assigned.</div>
        ) : (
          <table className={styles.table}>
            <thead><tr><th>Slug</th><th>Actions</th></tr></thead>
            <tbody>
              {policies.map(p => (
                <tr key={p.slug}>
                  <td><span className={styles.monoText}>{p.slug}</span></td>
                  <td>
                    <button type="button" className={`${styles.btn} ${styles.btnDanger}`}
                      onClick={() => void handleRemovePolicy(p.slug)}>Remove</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div className={styles.subsection}>
          <div className={styles.subsectionTitle}>Add Policy</div>
          <div className={styles.row}>
            <div className={styles.formGroup}>
              <select className={styles.select} value={assignSlug} onChange={e => setAssignSlug(e.target.value)}>
                <option value="">— select policy —</option>
                {allPolicies
                  .filter(p => !policies.some(ap => ap.slug === p.slug))
                  .map(p => <option key={p.slug} value={p.slug}>{p.slug}</option>)}
              </select>
            </div>
            <button type="button" className={`${styles.btn} ${styles.btnSecondary}`}
              onClick={handleAssignPolicy} disabled={!assignSlug}>
              Assign
            </button>
          </div>
        </div>
      </div>

      {isSuperuser && (
        <div className={styles.section}>
          <div className={styles.sectionTitle}>Policy Evaluator</div>
          <PolicyEvaluator typeId={udmType.id} />
        </div>
      )}
    </div>
  )
}

function TypesTab() {
  const { permissions } = usePermissions()
  const isSuperuser = !!permissions?.is_superuser
  const [types, setTypes] = useState<UDMTypeOut[]>([])
  const [configs, setConfigs] = useState<FieldConfigOut[]>([])
  const [allPolicies, setAllPolicies] = useState<PolicyOut[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedType, setSelectedType] = useState<UDMTypeOut | null>(null)
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [createError, setCreateError] = useState<string | null>(null)

  const loadAll = useCallback(async () => {
    setLoading(true)
    try {
      const [t, c, p] = await Promise.all([udmListTypes(), udmListConfigs(), udmListPolicies()])
      setTypes(t)
      setConfigs(c)
      setAllPolicies(p)
    } catch { /* ignore */ }
    setLoading(false)
  }, [])

  useEffect(() => { void loadAll() }, [loadAll])

  async function handleCreate() {
    setCreateError(null)
    if (!newName.trim()) { setCreateError('Name is required'); return }
    try {
      const t = await udmCreateType({ name: newName.trim(), description: newDesc })
      setTypes(prev => [...prev, t])
      setNewName('')
      setNewDesc('')
      setCreating(false)
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : 'Create failed')
    }
  }

  if (selectedType) {
    return (
      <TypeDetail
        udmType={selectedType}
        onBack={() => { setSelectedType(null); void loadAll() }}
        allConfigs={configs}
        allPolicies={allPolicies}
        onUpdated={updated => setSelectedType(updated)}
        isSuperuser={isSuperuser}
      />
    )
  }

  return (
    <div>
      <div className={styles.row} style={{ marginBottom: '1rem', justifyContent: 'flex-end' }}>
        <button type="button" className={`${styles.btn} ${styles.btnPrimary}`}
          onClick={() => setCreating(!creating)}>
          {creating ? 'Cancel' : '+ New UDM Type'}
        </button>
      </div>

      {creating && (
        <div className={styles.section}>
          <div className={styles.sectionTitle}>Create UDM Type</div>
          <div className={styles.row}>
            <div className={styles.formGroup}>
              <label className={styles.label}>Name *</label>
              <input className={styles.input} value={newName} onChange={e => setNewName(e.target.value)}
                placeholder="Workshop" />
            </div>
            <div className={styles.formGroup} style={{ flex: 2 }}>
              <label className={styles.label}>Description</label>
              <input className={styles.input} value={newDesc} onChange={e => setNewDesc(e.target.value)} />
            </div>
          </div>
          {createError && <div className={styles.error}>{createError}</div>}
          <div className={styles.row} style={{ marginTop: '0.75rem' }}>
            <button type="button" className={`${styles.btn} ${styles.btnPrimary}`} onClick={handleCreate}>
              Create
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <div className={styles.emptyState}>Loading…</div>
      ) : types.length === 0 ? (
        <div className={styles.emptyState}>No UDM types yet. Create one above.</div>
      ) : (
        <div className={styles.section}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Name</th>
                <th>Description</th>
                <th>Field Config</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {types.map(t => {
                const cfg = t.field_config_id ? configs.find(c => c.id === t.field_config_id) : null
                return (
                  <tr key={t.id}>
                    <td><strong>{t.name}</strong></td>
                    <td style={{ color: '#666', fontSize: '0.875rem' }}>{t.description || '—'}</td>
                    <td>{cfg ? cfg.name : <span style={{ color: '#999' }}>Not assigned</span>}</td>
                    <td>
                      <button type="button" className={`${styles.btn} ${styles.btnSecondary}`}
                        onClick={() => setSelectedType(t)}>
                        Manage
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export function UdmAdminPage() {
  useTranslation()
  const [tab, setTab] = useState<AdminTab>('configs')

  return (
    <div className={styles.page}>
      <h1 className={styles.pageTitle}>UDM Configuration Admin</h1>

      <div className={styles.tabs}>
        {([
          { key: 'configs', label: 'Field Configs' },
          { key: 'types', label: 'UDM Types' },
          { key: 'policies', label: 'Rego Policies' },
        ] as const).map(({ key, label }) => (
          <button key={key} type="button"
            className={`${styles.tab} ${tab === key ? styles.tabActive : ''}`}
            onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </div>

      {tab === 'configs' && <ConfigsTab />}
      {tab === 'types' && <TypesTab />}
      {tab === 'policies' && <PoliciesTab />}
    </div>
  )
}
