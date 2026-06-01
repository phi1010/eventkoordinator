import { useState, useEffect, useRef } from 'react'
import { Dropdown } from 'primereact/dropdown'
import { udmSearchEntities, udmGetEntity, udmGetConfigVersion } from '../apiUdm'
import type { EntityAutocompleteItem, EntityOut, ConfigVersionOut, FieldDefinitionOut } from '../apiUdm'
import { FieldPreview } from './FieldPreview'
import { getLang } from './types'
import { PreviewTable, type PreviewRow } from './PreviewTable'

export interface EntityComboboxProps {
  value: EntityAutocompleteItem | null
  onChange: (entity: EntityAutocompleteItem | null) => void
  typeId?: string
  disabled?: boolean
  placeholder?: string
  lang?: string
}

interface LoadedPreview { entity: EntityOut; config: ConfigVersionOut }

const MAX_PREVIEW_ITEMS = 30

function previewRowsFor(preview: LoadedPreview, lang: string): PreviewRow[] {
  const fields = preview.config.fields as FieldDefinitionOut[]
  const visible = fields.filter(f => f.is_preview).length > 0
    ? fields.filter(f => f.is_preview)
    : fields.slice(0, 3)
  return visible.map(fd => {
    const fv = preview.entity.field_values.find(v => v.field_slug === fd.slug && (v.language === lang || v.language === ''))
      ?? preview.entity.field_values.find(v => v.field_slug === fd.slug)
    return {
      key: fd.slug,
      label: getLang(fd.label as Record<string, string>, lang) || fd.slug,
      value: <FieldPreview fd={fd} value={fv?.value ?? null} lang={lang} entityChildren={preview.entity.children} />,
    }
  })
}

export function EntityCombobox({ value, onChange, typeId, disabled, placeholder = '— select entity —', lang = 'en' }: EntityComboboxProps) {
  const [options, setOptions] = useState<EntityAutocompleteItem[]>([])
  const [loading, setLoading] = useState(false)
  const [previewMap, setPreviewMap] = useState<Map<string, LoadedPreview>>(new Map())
  // Cache config versions so entities sharing the same config only fetch it once
  const configCache = useRef<Map<string, ConfigVersionOut>>(new Map())

  // Reload option list whenever the type filter changes
  useEffect(() => {
    setLoading(true)
    setPreviewMap(new Map())
    udmSearchEntities('', typeId || undefined)
      .then(setOptions)
      .catch(() => setOptions([]))
      .finally(() => setLoading(false))
  }, [typeId])

  // Batch-fetch entity previews for all loaded options (capped)
  useEffect(() => {
    if (options.length === 0) return
    const toFetch = options.slice(0, MAX_PREVIEW_ITEMS)
    let cancelled = false

    async function fetchPreview(opt: EntityAutocompleteItem): Promise<[string, LoadedPreview] | null> {
      try {
        const entity = await udmGetEntity(opt.id)
        let config = configCache.current.get(entity.config_version_id)
        if (!config) {
          config = await udmGetConfigVersion(entity.config_version_id)
          configCache.current.set(entity.config_version_id, config)
        }
        return [opt.id, { entity, config }]
      } catch {
        return null
      }
    }

    Promise.all(toFetch.map(fetchPreview)).then(results => {
      if (cancelled) return
      const map = new Map<string, LoadedPreview>()
      for (const r of results) if (r) map.set(r[0], r[1])
      setPreviewMap(map)
    })

    return () => { cancelled = true }
  }, [options])

  const itemTemplate = (item: EntityAutocompleteItem) => {
    const preview = previewMap.get(item.id)
    if (preview) {
      const rows = previewRowsFor(preview, lang)
      if (rows.length > 0) {
        return <PreviewTable rows={rows} title={item.display} borderless />
      }
    }
    // Fallback while loading or if entity has no preview fields — same table shape with available data
    return (
      <PreviewTable
        title={item.display}
        borderless
        rows={[{ key: 'id', label: 'ID', value: <span style={{ fontFamily: 'monospace', fontSize: '0.82rem' }}>{item.id.slice(0, 8)}…</span> }]}
      />
    )
  }

  const valueTemplate = (item: EntityAutocompleteItem | null) => {
    if (!item) return <span style={{ color: '#9ca3af' }}>{placeholder}</span>
    return <span style={{ fontSize: '0.9rem', fontWeight: 500 }}>{item.display}</span>
  }

  return (
    <Dropdown
      value={value}
      options={options}
      optionLabel="display"
      onChange={e => onChange((e.value as EntityAutocompleteItem) ?? null)}
      filter
      filterBy="display,id"
      showClear
      loading={loading}
      disabled={disabled}
      placeholder={placeholder}
      itemTemplate={itemTemplate}
      valueTemplate={valueTemplate}
      style={{ width: '100%' }}
      emptyFilterMessage="No entities found"
      emptyMessage={loading ? 'Loading…' : 'No entities'}
      panelStyle={{ minWidth: 320 }}
    />
  )
}
