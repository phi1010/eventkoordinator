import type { FieldInputProps } from './types'
import { fieldEditorRegistry } from './registry'
import styles from '../UdmEntityEditor.module.css'

function SlugIdEditor({ fd, value }: FieldInputProps) {
  const tc = fd.type_config as Record<string, unknown>
  const prefix = (tc['prefix'] as string) ?? ''
  const display = value != null ? `${prefix}-${value}` : '—'
  return (
    <input className={styles.input} type="text" value={display} disabled readOnly
      style={{ fontFamily: 'monospace', background: '#f5f5f5' }} />
  )
}

fieldEditorRegistry.register('slug_id', SlugIdEditor)
