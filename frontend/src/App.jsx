import { useEffect, useRef, useState } from 'react'
import LoginPage from './components/LoginPage'
import FolderPicker from './components/FolderPicker'
import Dashboard from './components/Dashboard'

const API_BASE = ''

async function fetchJSON(url, options) {
  const response = await fetch(url, options)
  let data = null
  try {
    data = await response.json()
  } catch {
    data = null
  }
  if (!response.ok) {
    const message = data?.detail || data?.message || response.statusText || 'Request failed'
    throw new Error(message)
  }
  return data
}

export default function App() {
  const [stage, setStage] = useState('loading')
  const [user, setUser] = useState(null)
  const [rootFolder, setRootFolder] = useState(null)
  const [bootstrapError, setBootstrapError] = useState('')
  const initialisedRef = useRef(false)

  useEffect(() => {
    if (initialisedRef.current) return
    initialisedRef.current = true

    const params = new URLSearchParams(window.location.search)
    if (params.get('auth')) {
      window.history.replaceState({}, '', window.location.pathname)
    }

    bootstrap()
  }, [])

  async function bootstrap() {
    try {
      const status = await fetchJSON(`${API_BASE}/api/status`)
      if (!status.authenticated) {
        setStage('login')
        return
      }

      const me = await fetchJSON(`${API_BASE}/auth/me`)
      setUser(me)
      setRootFolder(status.root_folder?.id ? status.root_folder : null)
      setStage(status.root_folder?.id ? 'syncing' : 'pick')
    } catch (err) {
      setBootstrapError(err.message)
      setStage('login')
    }
  }

  async function handleGoogleLogin() {
    window.location.href = 'http://localhost:8000/auth/login'
  }

  async function handleFolderSelected(folder) {
    await fetchJSON(`${API_BASE}/api/start-crawl`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ folder_id: folder.id, folder_name: folder.name }),
    })
    setRootFolder(folder)
    setStage('syncing')
  }

  async function handleChangeFolder() {
    setStage('pick')
  }

  async function handleLogout() {
    try {
      await fetchJSON('http://localhost:8000/auth/logout')
    } catch {
      // ignore logout failures and reset client state
    }
    setUser(null)
    setRootFolder(null)
    setStage('login')
  }

  if (stage === 'loading') {
    return (
      <div className="center-screen">
        <div className="panel glass" style={{ padding: 24, minWidth: 260 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div className="skeleton" style={{ width: 18, height: 18, borderRadius: 999 }} />
            <div className="mono muted">Initializing Drive Connector…</div>
          </div>
        </div>
      </div>
    )
  }

  if (stage === 'login') {
    return <LoginPage onLogin={handleGoogleLogin} error={bootstrapError} />
  }

  if (stage === 'pick') {
    return <FolderPicker user={user} onBack={handleLogout} onSelectFolder={handleFolderSelected} />
  }

  return (
    <Dashboard
      user={user}
      rootFolder={rootFolder}
      onChangeFolder={handleChangeFolder}
      onLogout={handleLogout}
    />
  )
}
