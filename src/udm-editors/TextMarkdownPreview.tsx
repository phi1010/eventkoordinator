import ReactMarkdown from 'react-markdown'
import type { PreviewProps } from './FieldPreview'
import { fieldPreviewRegistry } from './registry-preview'

function TextMarkdownPreview({ value }: PreviewProps) {
  const text = (value as string) ?? ''
  if (!text) return <span style={{ color: '#9ca3af' }}>—</span>
  return (
    <div style={{ fontSize: '0.9rem', color: '#374151', lineHeight: 1.5 }}>
      <ReactMarkdown>{text}</ReactMarkdown>
    </div>
  )
}

fieldPreviewRegistry.register('text_markdown', TextMarkdownPreview)
