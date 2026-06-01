import { Dropdown } from 'primereact/dropdown'
import type { FieldInputProps } from './types'
import { fieldEditorRegistry } from './registry'

function SelectSingleEditor({ fd, value, onChange, disabled }: FieldInputProps) {
  const tc = fd.type_config as Record<string, unknown>
  const choices = (tc['choices'] as string[]) ?? []
  const options = choices.map(c => ({ label: c, value: c }))
  return (
    <Dropdown
      options={options}
      value={(value as string) ?? null}
      onChange={e => onChange((e.value as string) ?? null)}
      filter={choices.length > 5}
      showClear
      disabled={disabled}
      placeholder="— select —"
      style={{ width: '100%' }}
    />
  )
}

fieldEditorRegistry.register('select_single', SelectSingleEditor)
