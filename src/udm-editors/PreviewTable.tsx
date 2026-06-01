import type React from 'react'

export interface PreviewRow {
  key: string
  label: string
  value: React.ReactNode
}

interface PreviewTableProps {
  rows: PreviewRow[]
  title?: string
  /** Remove the outer border/background — use inside an already-bordered container */
  borderless?: boolean
}

export function PreviewTable({ rows, title, borderless }: PreviewTableProps) {
  if (rows.length === 0) return null
  return (
    <div style={borderless ? { fontSize: '0.875rem' } : { border: '1px solid #e5e7eb', borderRadius: 6, background: '#f9fafb', overflow: 'hidden', fontSize: '0.875rem' }}>
      {title && (
        <div style={{ padding: '4px 10px', borderBottom: '1px solid #e5e7eb', fontWeight: 600, fontSize: '0.78rem', color: '#6b7280', background: '#f3f4f6', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
          {title}
        </div>
      )}
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <tbody>
          {rows.map((row, i) => (
            <tr key={row.key} style={{ borderBottom: i < rows.length - 1 ? '1px solid #f3f4f6' : undefined }}>
              <td style={{ padding: '5px 10px', fontSize: '0.8rem', color: '#6b7280', width: '38%', verticalAlign: 'top', fontWeight: 500, whiteSpace: 'nowrap' }}>
                {row.label}
              </td>
              <td style={{ padding: '5px 10px', verticalAlign: 'top', color: '#111827' }}>
                {row.value}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
