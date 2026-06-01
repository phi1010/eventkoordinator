import type { PreviewProps } from './FieldPreview'
import { fieldPreviewRegistry } from './registry-preview'

function SubmodelPreview({ value }: PreviewProps) {
  if (value == null) return <span style={{ color: '#9ca3af' }}>—</span>
  if (Array.isArray(value)) {
    const count = value.length
    return <span style={{ fontSize: '0.88rem', color: '#6b7280' }}>{count} item{count !== 1 ? 's' : ''}</span>
  }
  return <span style={{ fontSize: '0.88rem', color: '#6b7280' }}>1 item</span>
}

fieldPreviewRegistry.register(['submodel_list', 'submodel_select'], SubmodelPreview)
