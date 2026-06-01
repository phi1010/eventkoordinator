import type { FieldInputProps } from './types'
import { fieldEditorRegistry } from './registry'
import styles from '../UdmEntityEditor.module.css'

function makeNumberEditor(step: 'integer' | 'float') {
  return function NumberEditor({ value, onChange, disabled }: FieldInputProps) {
    return (
      <input className={styles.input} type="number" step={step === 'integer' ? '1' : 'any'}
        value={value != null ? String(value) : ''}
        onChange={e => onChange(e.target.value
          ? (step === 'integer' ? parseInt(e.target.value) : parseFloat(e.target.value))
          : null)}
        disabled={disabled} />
    )
  }
}

const IntegerEditor = makeNumberEditor('integer')
const FloatEditor = makeNumberEditor('float')

fieldEditorRegistry.register('integer', IntegerEditor)
fieldEditorRegistry.register('float', FloatEditor)
