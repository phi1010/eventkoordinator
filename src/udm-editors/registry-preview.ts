import type React from 'react'
import type { PreviewProps } from './FieldPreview'

export class FieldPreviewRegistry {
  private _map = new Map<string, React.ComponentType<PreviewProps>>()

  register(dataTypes: string | string[], component: React.ComponentType<PreviewProps>): void {
    const types = Array.isArray(dataTypes) ? dataTypes : [dataTypes]
    for (const dt of types) this._map.set(dt, component)
  }

  get(dataType: string): React.ComponentType<PreviewProps> | undefined {
    return this._map.get(dataType)
  }

  has(dataType: string): boolean {
    return this._map.has(dataType)
  }

  registeredTypes(): string[] {
    return [...this._map.keys()]
  }
}

export const fieldPreviewRegistry = new FieldPreviewRegistry()
