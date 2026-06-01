import { useState } from 'react'
import { udmTransitionEntity } from '../apiUdm'
import type { WorkflowDefinitionOut, WorkflowTransitionOut, FieldDefinitionOut } from '../apiUdm'
import type { FieldInputProps } from './types'
import { getLang } from './types'
import { fieldEditorRegistry } from './registry'
import styles from '../UdmEntityEditor.module.css'

function WorkflowCellEditor({ fd, value, disabled, lang = '', nodeId, onEntityRefresh }: FieldInputProps) {
  const wfDef = (fd as FieldDefinitionOut & { workflow_definition?: WorkflowDefinitionOut | null }).workflow_definition
  const currentStateName = (value as string | null) ?? null
  const currentState = wfDef?.states.find(s => s.name === currentStateName) ?? null
  const stateLabel = currentState
    ? getLang(currentState.label as Record<string, string>, lang || 'en') || currentStateName
    : currentStateName
  const availableTransitions: WorkflowTransitionOut[] = (wfDef?.transitions ?? []).filter(t => {
    if (t.from_undefined_only) return currentStateName === null
    if (t.from_state !== null) return t.from_state === currentStateName
    return true
  })
  const [childTransitioning, setChildTransitioning] = useState(false)

  async function handleChildTransition(transitionName: string) {
    if (!nodeId || !onEntityRefresh) return
    setChildTransitioning(true)
    try {
      const result = await udmTransitionEntity(nodeId, fd.slug, transitionName)
      await onEntityRefresh(result.policy_messages ?? [])
    } finally {
      setChildTransitioning(false)
    }
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
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
      {nodeId && onEntityRefresh && availableTransitions.map(t => {
        const tLabel = getLang(t.label as Record<string, string>, lang || 'en') || t.name
        return (
          <button
            key={t.name}
            type="button"
            className={styles.transitionBtn}
            disabled={disabled || childTransitioning}
            onClick={() => void handleChildTransition(t.name)}
          >
            {tLabel}
          </button>
        )
      })}
    </div>
  )
}

fieldEditorRegistry.register('workflow', WorkflowCellEditor)
