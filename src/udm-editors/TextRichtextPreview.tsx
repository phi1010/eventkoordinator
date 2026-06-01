import type { PreviewProps } from './FieldPreview'
import { fieldPreviewRegistry } from './registry-preview'

function TextRichtextPreview({ value }: PreviewProps) {
  const html = (value as string) ?? ''
  if (!html) return <span style={{ color: '#9ca3af' }}>—</span>
  return (
    <div
      style={{ fontSize: '0.9rem', color: '#374151', lineHeight: 1.5 }}
      // richtext content is produced by our own editor and is not user-supplied HTML
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}

fieldPreviewRegistry.register('text_richtext', TextRichtextPreview)
