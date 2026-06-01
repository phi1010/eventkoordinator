import { useState } from 'react'
import type { FieldDefinitionOut } from '../apiUdm'
import type { PreviewProps } from './FieldPreview'
import { FieldPreview } from './FieldPreview'
import { getLang } from './types'
import { PreviewTable, type PreviewRow } from './PreviewTable'
import { fieldPreviewRegistry } from './registry-preview'

interface ChildNode {
  id: string
  field_values: Array<{ field_slug: string; data_type: string; value: unknown; language: string }>
  children: Record<string, unknown[]>
}

function childValue(child: ChildNode, slug: string, lang: string): unknown {
  return child.field_values.find(fv => fv.field_slug === slug && (fv.language === lang || fv.language === ''))?.value
    ?? child.field_values.find(fv => fv.field_slug === slug)?.value
    ?? null
}

function ChildCard({ child, fields, lang, index }: { child: ChildNode; fields: FieldDefinitionOut[]; lang: string; index: number }) {
  const previewFields = fields.filter(f => f.is_preview)
  const visibleFields = previewFields.length > 0 ? previewFields : fields.slice(0, 4)

  // Use first preview field value as the card title, if it's a simple string
  const titleField = visibleFields[0]
  const titleValue = titleField ? childValue(child, titleField.slug, lang) : null
  const title = typeof titleValue === 'string' && titleValue
    ? titleValue
    : `Item ${index + 1}`

  const rows: PreviewRow[] = visibleFields.map(fd => ({
    key: fd.slug,
    label: getLang(fd.label as Record<string, string>, lang) || fd.slug,
    value: <FieldPreview fd={fd} value={childValue(child, fd.slug, lang)} lang={lang} entityChildren={child.children} />,
  }))

  return <PreviewTable title={title} rows={rows} />
}

function SubmodelPreview({ fd, entityChildren, lang = 'en' }: PreviewProps) {
  const [expanded, setExpanded] = useState(false)
  const children = (entityChildren?.[fd.slug] ?? []) as ChildNode[]
  const fields = (fd.submodel_config?.fields ?? []) as FieldDefinitionOut[]
  const count = children.length

  if (count === 0) return <span style={{ color: '#9ca3af' }}>—</span>

  return (
    <div>
      <button
        type="button"
        onClick={() => setExpanded(v => !v)}
        style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '0.88rem', color: '#2563eb', padding: 0, display: 'flex', alignItems: 'center', gap: 4 }}
      >
        <span>{expanded ? '▾' : '▸'}</span>
        <span>{count} item{count !== 1 ? 's' : ''}</span>
      </button>
      {expanded && (
        <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 6 }}>
          {children.map((child, i) => (
            <ChildCard key={child.id ?? i} child={child} fields={fields} lang={lang} index={i} />
          ))}
        </div>
      )}
    </div>
  )
}

fieldPreviewRegistry.register(['submodel_list', 'submodel_select'], SubmodelPreview)
