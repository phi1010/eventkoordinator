import createClient from 'openapi-fetch'
import type { paths, components } from './schema_udm'
import { getCsrfToken } from './api'

const CSRF_HEADER_NAME = 'X-CSRFToken'

const udmClient = createClient<paths>({
  baseUrl: '',
  fetch: async (request: Request) => {
    const token = await getCsrfToken()
    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(request.method)) {
      const headers = new Headers(request.headers)
      if (token) headers.set(CSRF_HEADER_NAME, token)
      return fetch(new Request(request, { headers, credentials: 'include' }))
    }
    return fetch(new Request(request, { credentials: 'include' }))
  },
})

// ── Type aliases ──────────────────────────────────────────────────────────────

export type FieldConfigOut = components['schemas']['FieldConfigOut']
export type FieldConfigCreateIn = components['schemas']['FieldConfigCreateIn']
export type FieldConfigUpdateIn = components['schemas']['FieldConfigUpdateIn']
export type ConfigVersionOut = components['schemas']['ConfigVersionOut']
export type ConfigDraftIn = components['schemas']['ConfigDraftIn']
export type FieldDefinitionIn = components['schemas']['FieldDefinitionIn']
export type FieldDefinitionOut = components['schemas']['FieldDefinitionOut']
export type ConfigLanguageOut = components['schemas']['ConfigLanguageOut']
export type ConfigLanguageIn = components['schemas']['ConfigLanguageIn']
export type PolicyOut = components['schemas']['PolicyOut']
export type PolicyCreateIn = components['schemas']['PolicyCreateIn']
export type PolicyUpdateIn = components['schemas']['PolicyUpdateIn']
export type PolicyAssignIn = components['schemas']['PolicyAssignIn']
export type UDMTypeOut = components['schemas']['UDMTypeOut']
export type UDMTypeCreateIn = components['schemas']['UDMTypeCreateIn']
export type EntityOut = components['schemas']['EntityOut']
export type EntityCreateIn = components['schemas']['EntityCreateIn']
export type EntityPatchIn = components['schemas']['EntityPatchIn']
export type FieldValueOut = components['schemas']['FieldValueOut']
export type WorkflowOut = components['schemas']['WorkflowOut']
export type WorkflowStateOut = components['schemas']['WorkflowStateOut']
export type WorkflowTransitionOut = components['schemas']['WorkflowTransitionOut']
export type WorkflowDefinitionIn = components['schemas']['WorkflowDefinitionIn']
export type DataType = components['schemas']['DataType']
export type TransitionIn = components['schemas']['TransitionIn']
export type EditHistoryOut = components['schemas']['EditHistoryOut']
export type UserAutocompleteItem = components['schemas']['UserAutocompleteItem']
export type GroupAutocompleteItem = components['schemas']['GroupAutocompleteItem']
export type EntityAutocompleteItem = components['schemas']['EntityAutocompleteItem']
export type StagingFileOut = components['schemas']['StagingFileOut']
export type MultiFieldRuleIn = components['schemas']['MultiFieldRuleIn']
export type MigrationPreviewOut = components['schemas']['MigrationPreviewOut']
export type RequiredRuleIn = components['schemas']['RequiredRuleIn']
export type MinLengthRuleIn = components['schemas']['MinLengthRuleIn']
export type MaxLengthRuleIn = components['schemas']['MaxLengthRuleIn']
export type RegexRuleIn = components['schemas']['RegexRuleIn']
export type MinValueRuleIn = components['schemas']['MinValueRuleIn']
export type MaxValueRuleIn = components['schemas']['MaxValueRuleIn']
export type MinItemsRuleIn = components['schemas']['MinItemsRuleIn']
export type MaxItemsRuleIn = components['schemas']['MaxItemsRuleIn']
export type MaxFileSizeRuleIn = components['schemas']['MaxFileSizeRuleIn']
export type AllowedMimeTypesRuleIn = components['schemas']['AllowedMimeTypesRuleIn']
export type RequiredInLanguageRuleIn = components['schemas']['RequiredInLanguageRuleIn']
export type AnyRuleIn =
  | RequiredRuleIn | MinLengthRuleIn | MaxLengthRuleIn | RegexRuleIn
  | MinValueRuleIn | MaxValueRuleIn | MinItemsRuleIn | MaxItemsRuleIn
  | MaxFileSizeRuleIn | AllowedMimeTypesRuleIn | RequiredInLanguageRuleIn
export type BulkMigrationOut = components['schemas']['BulkMigrationOut']
export type PolicyEvalOut = components['schemas']['PolicyEvalOut']

// Version list item returned by list_config_versions (content?: never in schema but backend returns JSON)
export interface ConfigVersionListItem {
  id: string
  status: string
  notes: string
  published_at: string | null
  created_at: string
}

// ── FieldConfig ───────────────────────────────────────────────────────────────

export async function udmListConfigs(): Promise<FieldConfigOut[]> {
  const { data, error, response } = await udmClient.GET('/api/udm/configs/')
  if (error || !response.ok) throw new Error('Failed to list configs')
  return data as FieldConfigOut[]
}

export async function udmCreateConfig(payload: FieldConfigCreateIn): Promise<FieldConfigOut> {
  const { data, error, response } = await udmClient.POST('/api/udm/configs/', { body: payload })
  if (error || !response.ok || !data) throw new Error('Failed to create config')
  return data as unknown as FieldConfigOut
}

export async function udmGetConfig(configId: string): Promise<FieldConfigOut> {
  const { data, error, response } = await udmClient.GET('/api/udm/configs/{config_id}/', {
    params: { path: { config_id: configId } },
  })
  if (error || !response.ok || !data) throw new Error('Config not found')
  return data as FieldConfigOut
}

export async function udmUpdateConfig(configId: string, payload: FieldConfigUpdateIn): Promise<FieldConfigOut> {
  const { data, error, response } = await udmClient.PATCH('/api/udm/configs/{config_id}/', {
    params: { path: { config_id: configId } },
    body: payload,
  })
  if (error || !response.ok || !data) throw new Error('Failed to update config')
  return data as FieldConfigOut
}

export async function udmDeleteConfig(configId: string): Promise<void> {
  const { error, response } = await udmClient.DELETE('/api/udm/configs/{config_id}/', {
    params: { path: { config_id: configId } },
  })
  if (error || !response.ok) throw new Error('Failed to delete config')
}

// ── Config Versions ───────────────────────────────────────────────────────────

export async function udmListConfigVersions(configId: string): Promise<ConfigVersionListItem[]> {
  const response = await fetch(`/api/udm/configs/${configId}/versions/`, { credentials: 'include' })
  if (!response.ok) throw new Error('Failed to list versions')
  return response.json() as Promise<ConfigVersionListItem[]>
}

export async function udmGetDraftVersion(configId: string): Promise<ConfigVersionOut> {
  const { data, error, response } = await udmClient.GET('/api/udm/configs/{config_id}/versions/draft/', {
    params: { path: { config_id: configId } },
  })
  if (error || !response.ok || !data) throw new Error('No draft version')
  return data as ConfigVersionOut
}

export async function udmGetPublishedVersion(configId: string): Promise<ConfigVersionOut> {
  const { data, error, response } = await udmClient.GET('/api/udm/configs/{config_id}/versions/published/', {
    params: { path: { config_id: configId } },
  })
  if (error || !response.ok || !data) throw new Error('No published version')
  return data as ConfigVersionOut
}

export async function udmReplaceDraft(configId: string, payload: ConfigDraftIn): Promise<ConfigVersionOut> {
  const { data, error, response } = await udmClient.PUT('/api/udm/configs/{config_id}/versions/draft/', {
    params: { path: { config_id: configId } },
    body: payload,
  })
  if (error || !response.ok || !data) throw new Error('Failed to replace draft')
  return data as ConfigVersionOut
}

export async function udmPublishDraft(configId: string): Promise<ConfigVersionOut> {
  const { data, error, response } = await udmClient.POST('/api/udm/configs/{config_id}/versions/draft/publish/', {
    params: { path: { config_id: configId } },
  })
  if (error || !response.ok || !data) throw new Error('Failed to publish draft')
  return data as ConfigVersionOut
}

// ── UDM Types ─────────────────────────────────────────────────────────────────

export async function udmListTypes(): Promise<UDMTypeOut[]> {
  const { data, error, response } = await udmClient.GET('/api/udm/types/')
  if (error || !response.ok) throw new Error('Failed to list types')
  return data as UDMTypeOut[]
}

export async function udmCreateType(payload: UDMTypeCreateIn): Promise<UDMTypeOut> {
  const { data, error, response } = await udmClient.POST('/api/udm/types/', { body: payload })
  if (error || !response.ok || !data) throw new Error('Failed to create type')
  return data as unknown as UDMTypeOut
}

export async function udmGetType(typeId: string): Promise<UDMTypeOut> {
  const { data, error, response } = await udmClient.GET('/api/udm/types/{type_id}/', {
    params: { path: { type_id: typeId } },
  })
  if (error || !response.ok || !data) throw new Error('Type not found')
  return data as UDMTypeOut
}

export async function udmEvalPolicy(
  typeId: string,
  entityId: string,
  userId: string,
  action: string,
  transition?: string,
): Promise<PolicyEvalOut> {
  const { data, error, response } = await udmClient.GET('/api/udm/types/{type_id}/eval-policy/', {
    params: {
      path: { type_id: typeId },
      query: { entity_id: entityId, user_id: userId, action, transition: transition ?? null },
    },
  })
  if (error || !response.ok || !data) throw new Error('Evaluation failed')
  return data as PolicyEvalOut
}

export async function udmGetTypeConfig(typeId: string): Promise<ConfigVersionOut> {
  const { data, error, response } = await udmClient.GET('/api/udm/types/{type_id}/config/', {
    params: { path: { type_id: typeId } },
  })
  if (error || !response.ok || !data) throw new Error('No config for type')
  return data as ConfigVersionOut
}

export async function udmUpdateType(typeId: string, fieldConfigId: string | null): Promise<UDMTypeOut> {
  const url = fieldConfigId
    ? `/api/udm/types/${typeId}/?field_config_id=${fieldConfigId}`
    : `/api/udm/types/${typeId}/`
  const token = await getCsrfToken()
  const resp = await fetch(url, {
    method: 'PATCH',
    credentials: 'include',
    headers: token ? { [CSRF_HEADER_NAME]: token } : {},
  })
  if (!resp.ok) throw new Error('Failed to update UDM type')
  return resp.json() as Promise<UDMTypeOut>
}

// ── Policies ──────────────────────────────────────────────────────────────────

export async function udmListPolicies(): Promise<PolicyOut[]> {
  const { data, error, response } = await udmClient.GET('/api/udm/policies/')
  if (error || !response.ok) throw new Error('Failed to list policies')
  return data as PolicyOut[]
}

export async function udmCreatePolicy(payload: PolicyCreateIn): Promise<PolicyOut> {
  const { data, error, response } = await udmClient.POST('/api/udm/policies/', { body: payload })
  if (error || !response.ok || !data) throw new Error('Failed to create policy')
  return data as unknown as PolicyOut
}

export async function udmUpdatePolicy(slug: string, payload: PolicyUpdateIn): Promise<PolicyOut> {
  const { data, error, response } = await udmClient.PUT('/api/udm/policies/{slug}/', {
    params: { path: { slug } },
    body: payload,
  })
  if (error || !response.ok || !data) throw new Error('Failed to update policy')
  return data as PolicyOut
}

export async function udmDeletePolicy(slug: string): Promise<void> {
  const { error, response } = await udmClient.DELETE('/api/udm/policies/{slug}/', {
    params: { path: { slug } },
  })
  if (error || !response.ok) throw new Error('Failed to delete policy')
}

export async function udmListTypePolicies(typeId: string): Promise<PolicyOut[]> {
  const { data, error, response } = await udmClient.GET('/api/udm/types/{type_id}/policies/', {
    params: { path: { type_id: typeId } },
  })
  if (error || !response.ok) throw new Error('Failed to list type policies')
  return data as PolicyOut[]
}

export async function udmAssignPolicy(typeId: string, payload: PolicyAssignIn): Promise<PolicyOut> {
  const { data, error, response } = await udmClient.POST('/api/udm/types/{type_id}/policies/', {
    params: { path: { type_id: typeId } },
    body: payload,
  })
  if (error || !response.ok || !data) throw new Error('Failed to assign policy')
  return data as unknown as PolicyOut
}

export async function udmRemovePolicy(typeId: string, slug: string): Promise<void> {
  const { error, response } = await udmClient.DELETE('/api/udm/types/{type_id}/policies/{slug}/', {
    params: { path: { type_id: typeId, slug } },
  })
  if (error || !response.ok) throw new Error('Failed to remove policy')
}

// ── Entities ──────────────────────────────────────────────────────────────────

export async function udmCreateEntity(payload: EntityCreateIn): Promise<EntityOut> {
  const { data, error, response } = await udmClient.POST('/api/udm/entities/', { body: payload })
  if (error || !response.ok || !data) throw new Error('Failed to create entity')
  return data as unknown as EntityOut
}

export async function udmGetEntity(entityId: string): Promise<EntityOut> {
  const { data, error, response } = await udmClient.GET('/api/udm/entities/{entity_id}/', {
    params: { path: { entity_id: entityId } },
  })
  if (error || !response.ok || !data) throw new Error('Entity not found')
  return data as EntityOut
}

export async function udmPatchEntity(entityId: string, changedFields: Record<string, unknown>): Promise<EntityOut> {
  const { data, error, response } = await udmClient.PATCH('/api/udm/entities/{entity_id}/', {
    params: { path: { entity_id: entityId } },
    body: { changed_fields: changedFields },
  })
  if (error || !response.ok || !data) throw new Error('Failed to patch entity')
  return data as EntityOut
}

export async function udmDeleteEntity(entityId: string): Promise<void> {
  const { error, response } = await udmClient.DELETE('/api/udm/entities/{entity_id}/', {
    params: { path: { entity_id: entityId } },
  })
  if (error || !response.ok) throw new Error('Failed to delete entity')
}

export async function udmTransitionEntity(entityId: string, transition: string): Promise<EntityOut> {
  const { data, error, response } = await udmClient.POST('/api/udm/entities/{entity_id}/transition/', {
    params: { path: { entity_id: entityId } },
    body: { transition },
  })
  if (error || !response.ok || !data) throw new Error('Transition failed')
  return data as EntityOut
}

export async function udmEntityHistory(entityId: string, page = 1): Promise<EditHistoryOut> {
  const { data, error, response } = await udmClient.GET('/api/udm/entities/{entity_id}/history/', {
    params: { path: { entity_id: entityId }, query: { page } },
  })
  if (error || !response.ok || !data) throw new Error('Failed to load history')
  return data as EditHistoryOut
}

// ── Autocomplete ──────────────────────────────────────────────────────────────

export async function udmSearchUsers(q = '', groupIds?: string): Promise<UserAutocompleteItem[]> {
  const { data, response } = await udmClient.GET('/api/udm/users/', {
    params: { query: { q, group_ids: groupIds } },
  })
  if (!response.ok) return []
  return (data as UserAutocompleteItem[]) || []
}

export async function udmSearchGroups(q = ''): Promise<GroupAutocompleteItem[]> {
  const { data, response } = await udmClient.GET('/api/udm/groups/', {
    params: { query: { q } },
  })
  if (!response.ok) return []
  return (data as GroupAutocompleteItem[]) || []
}

export async function udmSearchEntities(q = '', typeIds?: string): Promise<EntityAutocompleteItem[]> {
  const { data, response } = await udmClient.GET('/api/udm/entity-search/', {
    params: { query: { q, type_ids: typeIds } },
  })
  if (!response.ok) return []
  return (data as EntityAutocompleteItem[]) || []
}

// ── Staging files ─────────────────────────────────────────────────────────────

export async function udmUploadStagingFile(
  file: File,
  intendedFieldId?: string,
  onProgress?: (p: number) => void,
): Promise<StagingFileOut> {
  const token = await getCsrfToken()
  return new Promise<StagingFileOut>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    const url = intendedFieldId
      ? `/api/udm/staging-files/?intended_field_id=${intendedFieldId}`
      : '/api/udm/staging-files/'
    xhr.open('POST', url)
    xhr.withCredentials = true
    if (token) xhr.setRequestHeader('X-CSRFToken', token)
    xhr.upload.onprogress = (e) => {
      if (onProgress && e.lengthComputable && e.total > 0)
        onProgress(Math.min(100, Math.round((e.loaded / e.total) * 100)))
    }
    xhr.onerror = () => reject(new Error('Upload failed'))
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try { resolve(JSON.parse(xhr.responseText) as StagingFileOut) }
        catch { reject(new Error('Upload response unreadable')) }
      } else {
        reject(new Error(`Upload failed: ${xhr.status}`))
      }
    }
    const fd = new FormData()
    fd.append('file', file)
    onProgress?.(0)
    xhr.send(fd)
  })
}

export async function udmDeleteStagingFile(stagingId: string): Promise<void> {
  const { error, response } = await udmClient.DELETE('/api/udm/staging-files/{staging_id}/', {
    params: { path: { staging_id: stagingId } },
  })
  if (error || !response.ok) throw new Error('Failed to delete staging file')
}

// ── Bulk migration ────────────────────────────────────────────────────────────

export async function udmGetBulkMigration(planId: string): Promise<BulkMigrationOut> {
  const { data, error, response } = await udmClient.GET('/api/udm/bulk-migrations/{plan_id}/', {
    params: { path: { plan_id: planId } },
  })
  if (error || !response.ok || !data) throw new Error('Bulk migration not found')
  return data as BulkMigrationOut
}
