import type { FieldInputProps } from './types'
import { fieldEditorRegistry } from './registry'
import styles from '../UdmEntityEditor.module.css'

function BooleanEditor({ value, onChange, disabled }: FieldInputProps) {
  return (
    <label className={styles.checkbox}>
      <input type="checkbox" checked={!!value}
        onChange={e => onChange(e.target.checked)}
        disabled={disabled} />
      Yes
    </label>
  )
}

fieldEditorRegistry.register('boolean', BooleanEditor)
