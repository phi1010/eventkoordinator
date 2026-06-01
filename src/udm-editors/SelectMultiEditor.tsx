import type { FieldInputProps } from './types'
import { fieldEditorRegistry } from './registry'
import styles from '../UdmEntityEditor.module.css'

function SelectMultiEditor({ fd, value, onChange, disabled }: FieldInputProps) {
  const tc = fd.type_config as Record<string, unknown>
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

fieldEditorRegistry.register('select_multi', SelectMultiEditor)
