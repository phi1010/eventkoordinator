import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import HttpBackend from 'i18next-http-backend';
import LanguageDetector from 'i18next-browser-languagedetector';

i18n
  .use(HttpBackend)
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    fallbackLng: 'en',
    supportedLngs: ['en', 'de'],
    ns: ['translation'],
    defaultNS: 'translation',
    backend: { loadPath: `${import.meta.env.BASE_URL}locales/{{lng}}/{{ns}}.json` },
    detection: { order: ['navigator'] },
    interpolation: { escapeValue: false },
  });

import type enTranslation from '../public/locales/en/translation.json';

declare module 'i18next' {
  interface CustomTypeOptions {
    resources: { translation: typeof enTranslation };
  }
}

export default i18n;