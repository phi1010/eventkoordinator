import type { FieldInputProps } from './types'
import { fieldEditorRegistry } from './registry'
import styles from '../UdmEntityEditor.module.css'

function DateEditor({ value, onChange, disabled }: FieldInputProps) {
  return (
    <input className={styles.input} type="date" value={(value as string) ?? ''}
      onChange={e => onChange(e.target.value || null)} disabled={disabled} />
  )
}

function TimeEditor({ value, onChange, disabled }: FieldInputProps) {
  return (
    <input className={styles.input} type="time" value={(value as string) ?? ''}
      onChange={e => onChange(e.target.value || null)} disabled={disabled} />
  )
}

function DatetimeEditor({ value, onChange, disabled }: FieldInputProps) {
  const iso = value ? (value as string).replace(' ', 'T').slice(0, 16) : ''
  return (
    <input className={styles.input} type="datetime-local" value={iso}
      onChange={e => onChange(e.target.value ? e.target.value + ':00' : null)} disabled={disabled} />
  )
}

fieldEditorRegistry.register('date', DateEditor)
fieldEditorRegistry.register('time', TimeEditor)
fieldEditorRegistry.register('datetime', DatetimeEditor)
