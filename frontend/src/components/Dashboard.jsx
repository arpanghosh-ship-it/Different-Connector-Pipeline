import { Fragment, useEffect, useMemo, useRef, useState } from 'react'

const API_BASE = ''

async function fetchJSON(url) {
  const r = await fetch(url)
  const d = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(d?.detail || r.statusText)
  return d
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function getFileIcon(file) {
  const ext = (file.file_extension || '').replace('.', '')
  if (['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg'].includes(ext)) return '🖼'
  if (['mp4', 'mov', 'avi', 'mkv'].includes(ext))                  return '🎬'
  if (['mp3', 'wav', 'ogg'].includes(ext))                          return '🎵'
  if (ext === 'pdf')   return '📕'
  if (ext === 'docx')  return '📝'
  if (ext === 'xlsx')  return '📊'
  if (ext === 'pptx')  return '📋'
  if (ext === 'zip')   return '🗜'
  if (['txt', 'md', 'csv'].includes(ext)) return '📄'
  const t = file.file_type || ''
  if (t === 'gdoc')    return '📝'
  if (t === 'gsheet')  return '📊'
  if (t === 'gslides') return '📋'
  return '📁'
}

function getMimeBadge(file) {
  return file.file_type || file.mime_type?.split('/')[1]?.slice(0, 8) || '—'
}

function formatSize(bytes) {
  if (!bytes) return '—'
  if (bytes < 1024)          return `${bytes} B`
  if (bytes < 1024 * 1024)   return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatTime(iso) {
  if (!iso) return '—'
  try { return new Date(iso).toLocaleString() } catch { return iso }
}

function statusTone(status) {
  if (status === 'accessible') return 'badge-green'
  if (status === 'deleted')    return 'badge-red'
  if (status === 'updated')    return 'badge-cyan'
  return 'badge-muted'
}

function DetailItem({ label, value }) {
  return (
    <div className="detail-item">
      <span className="detail-label mono">{label}</span>
      <span className="detail-value">{value ?? '—'}</span>
    </div>
  )
}

function ConnectorBadge({ connector }) {
  if (connector === 'dropbox') {
    return <span className="badge" style={{ background: '#0061FF22', color: '#0061FF' }}>📦 Dropbox</span>
  }
  return <span className="badge badge-muted">📁 Google Drive</span>
}

function WebhookBadge({ webhook, connector }) {
  if (connector === 'dropbox') {
    return (
      <span className="badge badge-cyan" title="Dropbox webhooks are registered in the App Console">
        🔗 Dropbox Webhook (App Console)
      </span>
    )
  }
  if (!webhook) return <span className="badge badge-muted">Webhook: unknown</span>
  if (webhook.active) {
    return (
      <span className="badge badge-green" title={`Expires: ${webhook.expires_at}`}>
        🔗 Webhook active
      </span>
    )
  }
  return <span className="badge badge-red">⚠ Webhook inactive</span>
}

function ActivityFeed({ events, onClear }) {
  const bottomRef = useRef(null)
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events])

  const icons = {
    crawl_start:      '🚀',
    scan_start:       '🔍',
    file_found:       '📎',
    processing:       '⚙️',
    stored:           '✅',
    skipped:          '⏭',
    crawl_complete:   '🎉',
    error:            '❌',
    webhook_received: '📡',
    webhook_renewed:  '🔄',
    webhook_renewing: '⏳',
    webhook_stopped:  '🛑',
    ping:             null,
  }

  const visible = events.filter((e) => icons[e.type] !== null)

  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div className="card-header">
        <div>
          <div className="card-title">Live Activity</div>
          <div className="card-subtitle">Real-time sync events</div>
        </div>
        <button className="btn" type="button" onClick={onClear} style={{ fontSize: 11 }}>
          Clear
        </button>
      </div>
      <div className="scroll-area feed-area" style={{ flex: 1 }}>
        {visible.length === 0 ? (
          <div className="feed-empty">
            <div>
              <div className="feed-empty__icon">📡</div>
              <div>Waiting for events…</div>
            </div>
          </div>
        ) : (
          visible.map((ev, i) => (
            <div key={i} className="feed-item fade-in-up">
              <span className="feed-icon">{icons[ev.type] || '•'}</span>
              <div className="feed-body">
                <div className="feed-type mono">{ev.type}</div>
                <div className="feed-detail">
                  {ev.message || ev.file_name || ev.path || ''}
                </div>
                {ev.content_status && ev.content_status !== 'accessible' ? (
                  <span className={`badge ${statusTone(ev.content_status)}`} style={{ marginTop: 4, fontSize: 10 }}>
                    {ev.content_status}
                  </span>
                ) : null}
              </div>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}

// ── Main Dashboard ─────────────────────────────────────────────────────────────

export default function Dashboard({ user, rootFolder, connector, onChangeFolder, onLogout }) {
  const [files,        setFiles]        = useState([])
  const [events,       setEvents]       = useState([])
  const [webhook,      setWebhook]      = useState(null)
  const [isCrawling,   setIsCrawling]   = useState(false)
  const [loadingFiles, setLoadingFiles] = useState(true)
  const [search,       setSearch]       = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [sourceFilter, setSourceFilter] = useState('all')   // 'all' | 'drive' | 'dropbox'
  const [sortKey,      setSortKey]      = useState('folder_number')
  const [expanded,     setExpanded]     = useState({})
  const [reregistering, setReregistering] = useState(false)
  const [now,          setNow]          = useState(Date.now())

  const evtSourceRef = useRef(null)

  // ── Load files ──────────────────────────────────────────────────────────────
  async function loadFiles() {
    try {
      setLoadingFiles(true)
      const data = await fetchJSON(`${API_BASE}/api/files`)
      setFiles(
        (data.files || []).map((f) => ({
          ...f,
          __addedAt: Date.now(),
        }))
      )
    } catch (e) {
      console.error('loadFiles error:', e)
    } finally {
      setLoadingFiles(false)
    }
  }

  // ── Load webhook status ─────────────────────────────────────────────────────
  async function loadWebhookStatus() {
    try {
      const data = await fetchJSON(`${API_BASE}/api/webhook/status`)
      setWebhook(data)
    } catch { /* ignore */ }
  }

  // ── SSE connection ──────────────────────────────────────────────────────────
  useEffect(() => {
    loadFiles()
    loadWebhookStatus()

    const src = new EventSource(`${API_BASE}/api/events`)
    evtSourceRef.current = src

    src.onmessage = (e) => {
      try {
        const ev = JSON.parse(e.data)
        if (ev.type === 'ping') return

        pushEvent(ev)

        if (['crawl_start'].includes(ev.type))    setIsCrawling(true)
        if (['crawl_complete', 'error'].includes(ev.type)) {
          setIsCrawling(false)
          loadFiles()
        }
        if (ev.type === 'stored') loadFiles()
        if (['webhook_renewed', 'webhook_stopped'].includes(ev.type)) loadWebhookStatus()
      } catch { /* ignore */ }
    }

    const ticker = setInterval(() => setNow(Date.now()), 4000)
    return () => {
      src.close()
      clearInterval(ticker)
    }
  }, [])

  function pushEvent(ev) {
    setEvents((prev) => [...prev.slice(-200), ev])
  }

  // ── Webhook re-register (Drive only) ───────────────────────────────────────
  async function handleReregisterWebhook() {
    setReregistering(true)
    try {
      const result = await fetchJSON('/api/webhook/register')
      // fetchJSON doesn't support POST without options — use fetch directly
      const resp = await fetch('/api/webhook/register', { method: 'POST' })
      const data = await resp.json()
      setWebhook({ active: data.success, ...data })
      pushEvent({ type: 'webhook_renewed', message: `Webhook registered: ${data.callback_url}` })
    } catch (err) {
      pushEvent({ type: 'error', message: `Webhook registration failed: ${err.message}` })
    } finally {
      setReregistering(false)
    }
  }

  // ── Filter + sort ───────────────────────────────────────────────────────────
  const visibleFiles = useMemo(() => {
    const q = search.trim().toLowerCase()
    const filtered = files.filter((file) => {
      const matchText   = !q || `${file.file_name || ''} ${file.path || ''}`.toLowerCase().includes(q)
      const matchStatus = statusFilter === 'all' || file.content_status === statusFilter
      const matchSource = sourceFilter === 'all' || file.source_type === sourceFilter
      return matchText && matchStatus && matchSource
    })
    filtered.sort((a, b) => {
      if (sortKey === 'folder_number') return Number(a.folder_number || 0) - Number(b.folder_number || 0)
      if (sortKey === 'name')         return String(a.file_name || '').localeCompare(String(b.file_name || ''))
      if (sortKey === 'modified_at')  return new Date(a.modified_at || 0).getTime() - new Date(b.modified_at || 0).getTime()
      return 0
    })
    return filtered
  }, [files, search, statusFilter, sourceFilter, sortKey])

  function toggleExpanded(sourceId) {
    setExpanded((prev) => ({ ...prev, [sourceId]: !prev[sourceId] }))
  }

  const fileCount = files.length

  return (
    <div className="layout-grid">
      {/* ── Navbar ── */}
      <header className="navbar">
        <div className="navbar__left">
          <div className="brand">
            <div className="brand__title">Connector Pipeline</div>
            <div className="brand__sub">{rootFolder?.name || 'No folder selected'}</div>
          </div>
          <ConnectorBadge connector={connector} />
          <span className="badge badge-muted nav-chip">📁 {rootFolder?.name || 'Root'}</span>
        </div>

        <div className="navbar__center">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span className={`pulse-dot ${isCrawling ? 'pulse-dot--orange' : 'pulse-dot--green'}`} />
            <span className="mono muted">{isCrawling ? 'syncing…' : 'idle'}</span>
          </div>
          <span className="badge badge-muted">{fileCount} files stored</span>
          <WebhookBadge webhook={webhook} connector={connector} />

          {/* Re-register Drive webhook */}
          {connector === 'drive' && !webhook?.active && (
            <button
              className="btn btn-primary"
              type="button"
              onClick={handleReregisterWebhook}
              disabled={reregistering}
            >
              {reregistering ? 'Registering…' : '🔗 Register Webhook'}
            </button>
          )}
        </div>

        <div className="navbar__right">
          {user ? (
            <div className="badge badge-muted" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              {user.picture ? (
                <img src={user.picture} alt={user.email} style={{ width: 28, height: 28, borderRadius: 999 }} />
              ) : (
                <div className="file-icon" style={{ width: 28, height: 28 }}>
                  {connector === 'dropbox' ? '📦' : '👤'}
                </div>
              )}
              <div style={{ minWidth: 0 }}>
                <div className="mono" style={{ fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {user.email}
                </div>
                <div className="muted" style={{ fontSize: 11 }}>{user.name || 'Signed in'}</div>
              </div>
            </div>
          ) : null}
          <button className="btn" type="button" onClick={onChangeFolder}>Change folder</button>
          <button className="btn" type="button" onClick={onLogout}>Logout</button>
        </div>
      </header>

      {/* ── Body grid ── */}
      <div className="content-grid">
        <aside className="sidebar">
          <ActivityFeed events={events} onClear={() => setEvents([])} />
        </aside>

        <main className="main-panel">
          <div className="card" style={{ display: 'grid', gridTemplateRows: 'auto 1fr', height: '100%' }}>
            <div className="card-header" style={{ flexWrap: 'wrap' }}>
              <div>
                <div className="card-title">
                  <span>Synced Files</span>
                  <span className="badge badge-muted">{fileCount}</span>
                </div>
                <div className="card-subtitle">Real-time normalized document store</div>
              </div>

              <div className="files-toolbar" style={{ width: '100%' }}>
                <input
                  className="input"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search by file name or path…"
                />
                <select className="select" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                  <option value="all">All statuses</option>
                  <option value="accessible">Accessible</option>
                  <option value="updated">Updated</option>
                  <option value="deleted">Deleted</option>
                  <option value="inaccessible">Inaccessible</option>
                  <option value="too_large">Too large</option>
                  <option value="error">Error</option>
                </select>
                <select className="select" value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)}>
                  <option value="all">All connectors</option>
                  <option value="drive">Google Drive only</option>
                  <option value="dropbox">Dropbox only</option>
                </select>
                <select className="select" value={sortKey} onChange={(e) => setSortKey(e.target.value)}>
                  <option value="folder_number">Sort: folder #</option>
                  <option value="name">Sort: name</option>
                  <option value="modified_at">Sort: modified</option>
                </select>
                <div className="badge badge-muted">{loadingFiles ? 'Refreshing…' : 'Live'}</div>
              </div>
            </div>

            <div className="scroll-area">
              <table className="files-table">
                <thead>
                  <tr>
                    <th style={{ width: 40 }}>Src</th>
                    <th style={{ width: 56 }}>Type</th>
                    <th>File</th>
                    <th style={{ width: 90 }}>Badge</th>
                    <th style={{ width: 90 }}>Size</th>
                    <th style={{ width: 120 }}>Status</th>
                    <th style={{ width: 80 }}>Storage</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleFiles.length === 0 ? (
                    <tr>
                      <td colSpan={7} style={{ padding: 28 }}>
                        <div className="feed-empty" style={{ minHeight: 220 }}>
                          <div>
                            <div className="feed-empty__icon">🗂</div>
                            <div>{loadingFiles ? 'Loading files…' : 'No synced files yet'}</div>
                          </div>
                        </div>
                      </td>
                    </tr>
                  ) : visibleFiles.map((file) => {
                    const expandedRow = !!expanded[file.source_id]
                    const isNew = file.__addedAt && now - file.__addedAt < 5000

                    return (
                      <Fragment key={file.source_id}>
                        <tr
                          className={`file-row ${expandedRow ? 'file-row--expanded' : ''} ${isNew ? 'fade-in-up' : ''}`}
                          onClick={() => toggleExpanded(file.source_id)}
                        >
                          {/* Connector source icon */}
                          <td>
                            <span title={file.source_type}>
                              {file.source_type === 'dropbox' ? '📦' : '📁'}
                            </span>
                          </td>
                          <td><div className="file-icon">{getFileIcon(file)}</div></td>
                          <td>
                            <div className="file-name">{file.file_name}</div>
                            <div className="file-path">{file.path}</div>
                          </td>
                          <td><span className="badge badge-muted">{getMimeBadge(file)}</span>
                            {isNew ? <div style={{ marginTop: 8 }}><span className="badge badge-cyan">NEW</span></div> : null}
                          </td>
                          <td>{formatSize(file.size_bytes)}</td>
                          <td><span className={`badge ${statusTone(file.content_status)}`}>{file.content_status || '—'}</span></td>
                          <td className="mono">#{file.folder_number ?? '—'}</td>
                        </tr>

                        {expandedRow ? (
                          <tr className="expand-row">
                            <td colSpan={7} className="expand-cell">
                              <div className="detail-grid">
                                <DetailItem label="source_id"              value={file.source_id} />
                                <DetailItem label="source_type"            value={file.source_type} />
                                <DetailItem label="owner_email"            value={file.owner_email} />
                                <DetailItem label="modified_at"            value={formatTime(file.modified_at)} />
                                <DetailItem label="connector_synced_at"    value={formatTime(file.connector_synced_at)} />
                                <DetailItem label="shared"                 value={String(!!file.shared)} />
                                <DetailItem label="export_mime_type"       value={file.export_mime_type || '—'} />
                                <DetailItem label="raw_file_path"          value={file.raw_file_path || '—'} />
                                <DetailItem label="file_extension"         value={file.file_extension || '—'} />
                                <DetailItem label="file_type"              value={file.file_type || '—'} />
                                <DetailItem label="size_human"             value={file.size_human || '—'} />
                                <DetailItem label="parent_folder_id"       value={file.parent_folder_id || '—'} />
                                <DetailItem label="web_url"                value={file.web_url || '—'} />
                                {file.dropbox_content_hash ? (
                                  <DetailItem label="dropbox_content_hash" value={file.dropbox_content_hash} />
                                ) : null}
                              </div>
                            </td>
                          </tr>
                        ) : null}
                      </Fragment>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}