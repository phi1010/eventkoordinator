import type { FieldInputProps } from './types'
import { fieldEditorRegistry } from './registry'
import styles from '../UdmEntityEditor.module.css'

function SelectSingleEditor({ fd, value, onChange, disabled }: FieldInputProps) {
  const tc = fd.type_config as Record<string, unknown>
  const choices = (tc['choices'] as string[]) ?? []
  return (
    <select className={styles.select} value={(value as string) ?? ''}
      onChange={e => onChange(e.target.value || null)} disabled={disabled}>
      <option value="">— select —</option>
      {choices.map(c => <option key={c} value={c}>{c}</option>)}
    </select>
  )
}

fieldEditorRegistry.register('select_single', SelectSingleEditor)
