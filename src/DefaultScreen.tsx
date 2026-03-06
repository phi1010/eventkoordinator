import { useNavigate } from 'react-router-dom'
import { usePermissions } from './usePermissions'
import styles from './DefaultScreen.module.css'

export function DefaultScreen() {
  const navigate = useNavigate()
  const { canBrowse, canAdd, loading } = usePermissions()

  if (loading) {
    return (
      <div className={styles.container}>
        <div className={styles.content}>
          <p style={{ textAlign: 'center', color: '#666' }}>Loading...</p>
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
          <h1 className={styles.title}>Welcome to Event Coordinator</h1>
          <p style={{ textAlign: 'center', color: '#666', marginTop: '2rem' }}>
            You don't have permission to access any features.
            <br />
            Please log in or -- if that didn't work -- contact an administrator for access.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className={styles.container}>
      <div className={styles.content}>
        <h1 className={styles.title}>Welcome to Event Coordinator</h1>
        <p className={styles.subtitle}>Choose your role to get started</p>

        <div className={styles.buttonsGrid}>
          {canViewProposals && (
            <button
              className={styles.button}
              onClick={() => navigate('/proposal-editor')}
            >
              <div className={styles.buttonIcon}>🎤</div>
              <div className={styles.buttonTitle}>
                {canAdd('proposal') ? 'Create a Proposal' : 'View Proposals'}
              </div>
              <div className={styles.buttonDescription}>
                {canAdd('proposal')
                  ? 'Submit your workshop, talk, or activity proposal'
                  : 'View and manage your proposals'}
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
                {canAdd('series') || canAdd('event') ? 'Edit Schedule' : 'View Schedule'}
              </div>
              <div className={styles.buttonDescription}>
                {canAdd('series') || canAdd('event')
                  ? 'Manage events and coordinate the schedule'
                  : 'View the event schedule'}
              </div>
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
