import i18n from './i18n';

const tDynamic = i18n.t.bind(i18n) as (key: string) => string

export function translateApiError(code: string | null | undefined): string {
  if (code && i18n.exists(`api.${code}`)) {
    return tDynamic(`api.${code}`)
  }
  return tDynamic('api.common.internalError')
}