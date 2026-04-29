import i18n from './i18n';

export function translateApiError(code: string | null | undefined): string {
  if (code && i18n.exists(`api.${code}`)) {
    return i18n.t(`api.${code}` as Parameters<typeof i18n.t>[0]);
  }
  return i18n.t('api.common.internalError' as Parameters<typeof i18n.t>[0]);
}