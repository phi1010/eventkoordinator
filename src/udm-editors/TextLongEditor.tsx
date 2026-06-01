import type { FieldInputProps } from './types'
import { fieldEditorRegistry } from './registry'
import styles from '../UdmEntityEditor.module.css'

function TextLongEditor({ value, onChange, disabled }: FieldInputProps) {
  const len = ((value as string) ?? '').length
  return (
    <div>
      <textarea className={styles.textarea} rows={4} value={(value as string) ?? ''}
        onChange={e => onChange(e.target.value)} disabled={disabled} />
      <div className={styles.lenHint}>{len}</div>
    </div>
  )
}

fieldEditorRegistry.register('text_long', TextLongEditor)
