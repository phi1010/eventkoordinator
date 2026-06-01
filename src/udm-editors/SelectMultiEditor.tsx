import { MultiSelect } from 'primereact/multiselect'
import type { FieldInputProps } from './types'
import { fieldEditorRegistry } from './registry'

function SelectMultiEditor({ fd, value, onChange, disabled }: FieldInputProps) {
  const tc = fd.type_config as Record<string, unknown>
  const choices = (tc['choices'] as string[]) ?? []
  const options = choices.map(c => ({ label: c, value: c }))
  const selected: string[] = Array.isArray(value) ? value as string[] : []
  return (
    <MultiSelect
      options={options}
      value={selected}
      onChange={e => onChange(e.value as string[])}
      filter={choices.length > 5}
      display="chip"
      disabled={disabled}
      placeholder="Select options…"
      style={{ width: '100%' }}
    />
  )
}

fieldEditorRegistry.register('select_multi', SelectMultiEditor)
