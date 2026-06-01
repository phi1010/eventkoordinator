import type React from 'react'
import type { FieldInputProps } from './types'

export class FieldEditorRegistry {
  private _map = new Map<string, React.ComponentType<FieldInputProps>>()

  register(dataTypes: string | string[], component: React.ComponentType<FieldInputProps>): void {
    const types = Array.isArray(dataTypes) ? dataTypes : [dataTypes]
    for (const dt of types) this._map.set(dt, component)
  }

  get(dataType: string): React.ComponentType<FieldInputProps> | undefined {
    return this._map.get(dataType)
  }

  has(dataType: string): boolean {
    return this._map.has(dataType)
  }

  unregister(dataType: string): void {
    this._map.delete(dataType)
  }

  registeredTypes(): string[] {
    return [...this._map.keys()]
  }
}

export const fieldEditorRegistry = new FieldEditorRegistry()
