import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { usePermissions } from './usePermissions'
import styles from './DefaultScreen.module.css'

export function DefaultScreen() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { canBrowse, canAdd, loading } = usePermissions()

  if (loading) {
    return (
      <div className={styles.container}>
        <div className={styles.content}>
          <p style={{ textAlign: 'center', color: '#666' }}>{t('common.loading')}</p>
        </div>
      </div>
    )
  }

  const canViewProposals = canBrowse('proposal')
  const canViewSeries = canBrowse('series')

  // If user has no permissions to view anything, show a message
  if (!canViewProposals && !canViewSeries) {
    return (
      <div className={styles.container}>
        <div className={styles.content}>
          <h1 className={styles.title}>{t('defaultScreen.welcomeTitle')}</h1>
          <p style={{ textAlign: 'center', color: '#666', marginTop: '2rem' }}>
            {t('defaultScreen.noPermission')}
            <br />
            {t('defaultScreen.contactAdmin')}
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className={styles.container}>
      <div className={styles.content}>
        <h1 className={styles.title}>{t('defaultScreen.welcomeTitle')}</h1>
        <p className={styles.subtitle}>{t('defaultScreen.chooseRole')}</p>

        <div className={styles.buttonsGrid}>
          {canViewProposals && (
            <button
              className={styles.button}
              onClick={() => navigate('/proposal-editor')}
            >
              <div className={styles.buttonIcon}>🎤</div>
              <div className={styles.buttonTitle}>
                {canAdd('proposal') ? t('defaultScreen.createProposal') : t('defaultScreen.viewProposals')}
              </div>
              <div className={styles.buttonDescription}>
                {canAdd('proposal')
                  ? t('defaultScreen.createProposalDesc')
                  : t('defaultScreen.manageProposals')}
              </div>
            </button>
          )}

          {canViewSeries && (
            <button
              className={styles.button}
              onClick={() => navigate('/coordinator')}
            >
              <div className={styles.buttonIcon}>📅</div>
              <div className={styles.buttonTitle}>
                {canAdd('series') || canAdd('event') ? t('defaultScreen.editSchedule') : t('defaultScreen.viewSchedule')}
              </div>
              <div className={styles.buttonDescription}>
                {canAdd('series') || canAdd('event')
                  ? t('defaultScreen.editScheduleDesc')
                  : t('defaultScreen.viewScheduleDesc')}
              </div>
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
