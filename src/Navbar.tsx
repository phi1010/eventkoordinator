import { useState, useRef, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { initializeCsrfToken, login as apiLogin } from './api'
import { usePermissions } from './usePermissions'
import { translateApiError } from './apiError'
import { useTranslation } from 'react-i18next'
import i18n from './i18n'
import type { User } from './api'
import styles from './Navbar.module.css'

interface NavbarProps {
  user: User | null
  onLogin: (user: User) => void
  onLogout: () => void
}

export function Navbar({ user, onLogin, onLogout }: NavbarProps) {
  const { t } = useTranslation()
  const [isDropdownOpen, setIsDropdownOpen] = useState(false)
  const [loginFormData, setLoginFormData] = useState({ username: '', password: '' })
  const [loginError, setLoginError] = useState<string | null>(null)
  const [isLoggingIn, setIsLoggingIn] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const location = useLocation()
  const { canBrowse, permissions } = usePermissions()

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsDropdownOpen(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoginError(null)
    setIsLoggingIn(true)

    try {
      if (!loginFormData.username.trim() || !loginFormData.password.trim()) {
        setLoginError(t('api.common.invalidRequest'))
        return
      }

      const user = await apiLogin(loginFormData.username, loginFormData.password)
      onLogin(user)
      setLoginFormData({ username: '', password: '' })
      setIsDropdownOpen(false)
    } catch (error) {
      const code = error instanceof Error ? error.message : 'api.common.internalError'
      setLoginError(translateApiError(code))
      console.error('Login error:', error)
    } finally {
      setIsLoggingIn(false)
    }
  }

  const getCookieValue = (name: string): string => {
    const value = `; ${document.cookie}`
    const parts = value.split(`; ${name}=`)
    if (parts.length === 2) {
      return parts.pop()?.split(';').shift() ?? ''
    }
    return ''
  }

  const handleLogout = async () => {
    onLogout()
    setIsDropdownOpen(false)

    await initializeCsrfToken()

    // OIDC logout endpoint expects POST; submit a real form so redirects leave the SPA.
    const form = document.createElement('form')
    form.method = 'POST'
    form.action = '/oidc/logout/'

    const csrfInput = document.createElement('input')
    csrfInput.type = 'hidden'
    csrfInput.name = 'csrfmiddlewaretoken'
    csrfInput.value = getCookieValue('csrftoken')
    form.appendChild(csrfInput)

    const nextInput = document.createElement('input')
    nextInput.type = 'hidden'
    nextInput.name = 'next'
    nextInput.value = '/'
    form.appendChild(nextInput)

    document.body.appendChild(form)
    form.submit()
  }

  const handleSsoLogin = () => {
    const next = `${location.pathname}${location.search}`
    window.location.href = `/oidc/authenticate/?next=${encodeURIComponent(next)}`
  }

  return (
    <nav className={styles.navbar} aria-label="Main navigation">
      <div className={styles.container}>
        <Link to="/" className={styles.logo} aria-label={`${t('nav.appName')} – ${t('nav.goToHome')}`}>
          <h1>{t('nav.appName')}</h1>
        </Link>

        <div className={styles.navLinks} role="list">
          {canBrowse('series') && (
            <Link
              role="listitem"
              className={location.pathname.startsWith('/coordinator') ? styles.activeNavLink : styles.navLink}
              to="/coordinator"
              aria-current={location.pathname.startsWith('/coordinator') ? 'page' : undefined}
            >
              {t('nav.coordinator')}
            </Link>
          )}
          {canBrowse('proposal') && (
            <Link
              role="listitem"
              className={location.pathname === '/proposal-editor' ? styles.activeNavLink : styles.navLink}
              to="/proposal-editor"
              aria-current={location.pathname === '/proposal-editor' ? 'page' : undefined}
            >
              {t('nav.proposalEditor')}
            </Link>
          )}
          {permissions?.is_staff && (
            <a
              role="listitem"
              className={styles.navLink}
              href="/admin/"
              aria-label={t('nav.adminLink')}
            >
              {t('nav.adminPanel')}
            </a>
          )}
        </div>

        <div className={styles.langSwitcher} aria-label="Language switcher">
          <button
            type="button"
            className={`${styles.langButton} ${i18n.language.startsWith('en') ? styles.langButtonActive : ''}`}
            onClick={() => void i18n.changeLanguage('en')}
            aria-label="Switch to English"
            aria-pressed={i18n.language.startsWith('en')}
          >
            🇬🇧
          </button>
          <button
            type="button"
            className={`${styles.langButton} ${i18n.language.startsWith('de') ? styles.langButtonActive : ''}`}
            onClick={() => void i18n.changeLanguage('de')}
            aria-label="Auf Deutsch wechseln"
            aria-pressed={i18n.language.startsWith('de')}
          >
            🇩🇪
          </button>
        </div>

        <div className={styles.menu} ref={dropdownRef}>
          <button
            type="button"
            className={styles.menuButton}
            onClick={() => setIsDropdownOpen(!isDropdownOpen)}
            aria-expanded={isDropdownOpen}
            aria-haspopup="true"
            aria-label="User menu"
          >
            <span className={styles.userIcon} aria-hidden="true">👤</span>
            <span className={styles.username}>
              {user ? user.username : t('nav.guest')}
            </span>
            <span className={styles.chevron} aria-hidden="true">▼</span>
          </button>

          {isDropdownOpen && (
            <div className={styles.dropdown} role="menu" aria-label="User options">
              {user ? (
                <>
                  <div className={styles.userInfo}>
                    <span className={styles.infoLabel}>{t('nav.loggedInAs')}</span>
                    <span className={styles.infoValue}>{user.username}</span>
                  </div>
                  <hr className={styles.divider} />
                  <button
                    type="button"
                    className={styles.logoutButton}
                    onClick={handleLogout}
                    role="menuitem"
                  >
                    {t('common.logout')}
                  </button>
                </>
              ) : (
                <form
                  className={styles.loginForm}
                  onSubmit={handleLoginSubmit}
                  aria-label="Login form"
                >
                  <button
                    type="button"
                    className={styles.ssoButton}
                    onClick={handleSsoLogin}
                    aria-label={t('nav.loginWithSso')}
                  >
                    {t('nav.loginWithSso')}
                  </button>
                  <div className={styles.ssoHint} aria-hidden="true">{t('nav.ssoHint')}</div>
                  {loginError && (
                    <div className={styles.errorMessage} role="alert">{loginError}</div>
                  )}
                  <div className={styles.formGroup}>
                    <label htmlFor="username" className={styles.label}>
                      {t('nav.username')}
                    </label>
                    <input
                      id="username"
                      type="text"
                      className={styles.input}
                      placeholder={t('nav.enterUsername')}
                      value={loginFormData.username}
                      onChange={(e) =>
                        setLoginFormData({ ...loginFormData, username: e.target.value })
                      }
                      disabled={isLoggingIn}
                      autoFocus
                      autoComplete="username"
                    />
                  </div>
                  <div className={styles.formGroup}>
                    <label htmlFor="password" className={styles.label}>
                      {t('nav.password')}
                    </label>
                    <input
                      id="password"
                      type="password"
                      className={styles.input}
                      placeholder={t('nav.enterPassword')}
                      value={loginFormData.password}
                      onChange={(e) =>
                        setLoginFormData({ ...loginFormData, password: e.target.value })
                      }
                      disabled={isLoggingIn}
                      autoComplete="current-password"
                    />
                  </div>
                  <button
                    type="submit"
                    className={styles.loginButton}
                    disabled={!loginFormData.username.trim() || !loginFormData.password.trim() || isLoggingIn}
                    aria-busy={isLoggingIn}
                  >
                    {isLoggingIn ? t('nav.loggingIn') : t('common.login')}
                  </button>
                </form>
              )}
            </div>
          )}
        </div>
      </div>
    </nav>
  )
}
