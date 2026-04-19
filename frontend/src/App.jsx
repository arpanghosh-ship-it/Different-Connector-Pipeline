import { useEffect, useRef, useState } from 'react'
import LoginPage from './components/LoginPage'
import FolderPicker from './components/FolderPicker'
import DropboxFolderPicker from './components/DropboxFolderPicker'
import Dashboard from './components/Dashboard'

const API_BASE = ''

async function fetchJSON(url, options) {
  const response = await fetch(url, options)
  let data = null
  try { data = await response.json() } catch { data = null }
  if (!response.ok) {
    const message = data?.detail || data?.message || response.statusText || 'Request failed'
    throw new Error(message)
  }
  return data
}

export default function App() {
  // stage: 'loading' | 'login' | 'pick' | 'dropbox-pick' | 'syncing'
  const [stage,           setStage]           = useState('loading')
  const [user,            setUser]            = useState(null)
  const [rootFolder,      setRootFolder]      = useState(null)
  const [activeConnector, setActiveConnector] = useState('drive')  // 'drive' | 'dropbox'
  const [bootstrapError,  setBootstrapError]  = useState('')
  const initialisedRef = useRef(false)

  useEffect(() => {
    if (initialisedRef.current) return
    initialisedRef.current = true

    const params        = new URLSearchParams(window.location.search)
    const authResult    = params.get('auth')
    const authConnector = params.get('connector')
    if (authResult) {
      window.history.replaceState({}, '', window.location.pathname)
    }

    // If Dropbox callback redirected here with success
    if (authResult === 'success' && authConnector === 'dropbox') {
      bootstrap('dropbox')
      return
    }

    bootstrap()
  }, [])

  async function bootstrap(preferredConnector = null) {
    try {
      const status = await fetchJSON(`${API_BASE}/api/status`)

      // ── Dropbox preferred (just logged in via Dropbox) ──────────
      if (preferredConnector === 'dropbox' || status.dropbox_authenticated) {
        if (status.dropbox_authenticated) {
          const me = await fetchJSON(`${API_BASE}/dropbox/me`)
          setUser({ ...me, provider: 'dropbox' })
          setActiveConnector('dropbox')

          const dbxRoot = status.dropbox_root_folder
          if (dbxRoot?.path) {
            setRootFolder({ id: dbxRoot.path, name: dbxRoot.name })
            setStage('syncing')
          } else {
            setStage('dropbox-pick')
          }
          return
        }
      }

      // ── Google Drive ─────────────────────────────────────────────
      if (status.authenticated) {
        const me = await fetchJSON(`${API_BASE}/auth/me`)
        setUser({ ...me, provider: 'drive' })
        setActiveConnector('drive')
        setRootFolder(status.root_folder?.id ? status.root_folder : null)
        setStage(status.root_folder?.id ? 'syncing' : 'pick')
        return
      }

      // Neither authenticated
      setStage('login')

    } catch (err) {
      setBootstrapError(err.message)
      setStage('login')
    }
  }

  // ── Google Drive login ─────────────────────────────────────────────────────
  async function handleGoogleLogin() {
    window.location.href = `${window.location.origin}/auth/login`
  }

  // ── Dropbox login ──────────────────────────────────────────────────────────
  async function handleDropboxLogin() {
    window.location.href = `${window.location.origin}/dropbox/login`
  }

  // ── Google Drive folder selected ───────────────────────────────────────────
  async function handleDriveFolderSelected(folder) {
    await fetchJSON(`${API_BASE}/api/start-crawl`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ folder_id: folder.id, folder_name: folder.name }),
    })
    setRootFolder(folder)
    setStage('syncing')
  }

  // ── Dropbox folder selected ────────────────────────────────────────────────
  async function handleDropboxFolderSelected(folder) {
    await fetchJSON(`${API_BASE}/api/dropbox/start-crawl`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ path: folder.id, name: folder.name }),
    })
    setRootFolder({ id: folder.id, name: folder.name })
    setStage('syncing')
  }

  // ── Logout ─────────────────────────────────────────────────────────────────
  async function handleLogout() {
    try {
      if (activeConnector === 'dropbox') {
        await fetch(`${API_BASE}/dropbox/logout`)
      } else {
        await fetch(`${API_BASE}/auth/logout`)
      }
    } catch {
      // ignore logout failures and reset client state
    }
    setUser(null)
    setRootFolder(null)
    setStage('login')
  }

  async function handleChangeFolder() {
    setStage(activeConnector === 'dropbox' ? 'dropbox-pick' : 'pick')
  }

  // ── Render ─────────────────────────────────────────────────────────────────
  if (stage === 'loading') {
    return (
      <div className="center-screen">
        <div className="panel glass" style={{ padding: 24, minWidth: 260 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div className="skeleton" style={{ width: 18, height: 18, borderRadius: 999 }} />
            <div className="mono muted">Initializing Connector Pipeline…</div>
          </div>
        </div>
      </div>
    )
  }

  if (stage === 'login') {
    return (
      <LoginPage
        onGoogleLogin={handleGoogleLogin}
        onDropboxLogin={handleDropboxLogin}
        error={bootstrapError}
      />
    )
  }

  if (stage === 'pick') {
    return (
      <FolderPicker
        user={user}
        onBack={() => setStage('login')}
        onSelectFolder={handleDriveFolderSelected}
      />
    )
  }

  if (stage === 'dropbox-pick') {
    return (
      <DropboxFolderPicker
        user={user}
        onBack={() => setStage('login')}
        onSelectFolder={handleDropboxFolderSelected}
      />
    )
  }

  // stage === 'syncing'
  return (
    <Dashboard
      user={user}
      rootFolder={rootFolder}
      connector={activeConnector}
      onChangeFolder={handleChangeFolder}
      onLogout={handleLogout}
    />
  )
}
