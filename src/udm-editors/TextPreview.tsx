import type { PreviewProps } from './FieldPreview'
import { fieldPreviewRegistry } from './registry-preview'

function TextPreview({ value }: PreviewProps) {
  const text = (value as string) ?? ''
  if (!text) return <span style={{ color: '#9ca3af' }}>—</span>
  return <span style={{ fontSize: '0.9rem', color: '#374151', whiteSpace: 'pre-wrap' }}>{text}</span>
}

fieldPreviewRegistry.register(['text_short', 'text_long'], TextPreview)
