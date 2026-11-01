import i18n from 'i18next'
import { createElement, useEffect, type ReactNode } from 'react'
import { I18nextProvider, initReactI18next } from 'react-i18next'

import en from './locales/en'
import zh from './locales/zh'

export type Language = 'zh' | 'en'

export function detectLanguage(): Language {
  return navigator.language.toLowerCase().startsWith('zh') ? 'zh' : 'en'
}

export function setupI18n(language: Language = detectLanguage()) {
  if (!i18n.isInitialized) {
    void i18n.use(initReactI18next).init({
      resources: { zh: { translation: zh }, en: { translation: en } },
      lng: language,
      fallbackLng: 'en',
      initAsync: false,
      interpolation: { escapeValue: false },
    })
  } else if (i18n.language !== language) {
    void i18n.changeLanguage(language)
  }
  return i18n
}

setupI18n()

export function I18nProvider({
  language,
  children,
}: {
  language: Language
  children: ReactNode
}) {
  useEffect(() => {
    if (i18n.language !== language) {
      void i18n.changeLanguage(language)
    }
  }, [language])

  return createElement(I18nextProvider, { i18n }, children)
}
