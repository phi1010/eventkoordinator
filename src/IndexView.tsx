import { useState, useEffect } from 'react'
import { Routes, Route } from 'react-router-dom'
import { Navbar } from './Navbar'
import { DefaultScreen } from './DefaultScreen'
import { MainView } from './MainView'
import { ProposalSelectionPanel } from './SelectionPanel'
import { SyncDiff } from './SyncDiff'
import { getCurrentUser, initializeCsrfToken, type User } from './api'
import { usePermissions, notifyAuthChanged } from './usePermissions'
import styles from './IndexView.module.css'

export function IndexView() {
  const [user, setUser] = useState<User | null>(null)
  const { canBrowse, loading: permissionsLoading } = usePermissions()

  useEffect(() => {
    const initializeApp = async () => {
      await initializeCsrfToken()
      try {
        const currentUser = await getCurrentUser()
        setUser(currentUser)
      } catch {
        console.log('User not authenticated')
      }
    }
    initializeApp()
  }, [])

  const handleLogin = (authenticatedUser: User) => {
    setUser(authenticatedUser)
    notifyAuthChanged()
  }

  const handleLogout = () => {
    setUser(null)
    notifyAuthChanged()
  }

  return (
    <div className={styles.layout}>
      <Navbar user={user} onLogin={handleLogin} onLogout={handleLogout} />
      <main className={styles.main}>
        <Routes>
          <Route path="/" element={<DefaultScreen />} />
          <Route
            path="/coordinator/:seriesId?/:eventId?"
            element={
              permissionsLoading ? null : canBrowse('series') ? <MainView /> : (
                <div style={{ padding: '2rem', textAlign: 'center', color: '#666' }}>
                  <p style={{ fontSize: '1.2rem', marginBottom: '1rem' }}>Access Denied</p>
                  <p>You don't have permission to browse series</p>
                </div>
              )
            }
          />
          <Route
            path="/proposal-editor/:proposalId?"
            element={
              permissionsLoading ? null : canBrowse('proposal') ? <ProposalSelectionPanel /> : (
                <div style={{ padding: '2rem', textAlign: 'center', color: '#666' }}>
                  <p style={{ fontSize: '1.2rem', marginBottom: '1rem' }}>Access Denied</p>
                  <p>You don't have permission to browse proposals</p>
                </div>
              )
            }
          />
          <Route
            path="/sync/diff/:seriesId/:eventId/:platform"
            element={<SyncDiff />}
          />
        </Routes>
      </main>
    </div>
  )
}
