import { Fragment, useEffect, useMemo, useRef, useState } from 'react'

async function fetchJSON(url, options) {
  const response = await fetch(url, options)
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(data?.detail || data?.message || response.statusText || 'Request failed')
  }
  return data
}

function formatTime(value) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return value
  }
}

function formatSize(bytes) {
  if (bytes === null || bytes === undefined || bytes === '') return '—'
  const n = Number(bytes)
  if (Number.isNaN(n)) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 ** 3) return `${(n / (1024 ** 2)).toFixed(1)} MB`
  return `${(n / (1024 ** 3)).toFixed(2)} GB`
}

function getMimeBadge(file) {
  return file.file_type || file.file_extension?.replace('.', '') || file.mime_type?.split('/').pop()?.slice(0, 10) || 'file'
}

function getFileIcon(file) {
  const label = `${file.mime_type || ''} ${file.file_extension || ''} ${file.file_type || ''}`.toLowerCase()
  if (label.includes('folder')) return '📁'
  if (label.includes('pdf')) return '📄'
  if (label.includes('sheet') || label.includes('csv') || label.includes('xlsx') || label.includes('spread')) return '📊'
  if (label.includes('doc') || label.includes('txt')) return '📝'
  if (label.includes('slide') || label.includes('ppt')) return '📽️'
  if (label.includes('image') || label.includes('png') || label.includes('jpg') || label.includes('jpeg')) return '🖼️'
  if (label.includes('video') || label.includes('mp4') || label.includes('mov')) return '🎞️'
  if (label.includes('audio') || label.includes('mp3') || label.includes('wav')) return '🎵'
  return '📄'
}

function statusTone(status) {
  switch (status) {
    case 'accessible': return 'badge-green'
    case 'inaccessible': return 'badge-orange'
    case 'too_large': return 'badge-yellow'
    case 'deleted': return 'badge-red'
    case 'error': return 'badge-red'
    default: return 'badge-muted'
  }
}

function eventTone(type) {
  if (type === 'error') return 'feed-item--error'
  if (type === 'stored') return 'feed-item--stored'
  return ''
}

function eventIcon(type) {
  switch (type) {
    case 'crawl_start': return '🧭'
    case 'scan_start': return '📂'
    case 'file_found': return '🔎'
    case 'processing': return '⏳'
    case 'stored': return '✅'
    case 'skipped': return '↷'
    case 'poll_start': return '⏱️'
    case 'poll_complete': return '↻'
    case 'poll_skip': return '⏭️'
    case 'crawl_complete': return '🏁'
    case 'error': return '⛔'
    default: return '•'
  }
}

function eventColor(type) {
  switch (type) {
    case 'crawl_start':
    case 'scan_start': return 'badge-cyan'
    case 'file_found': return 'badge-yellow'
    case 'processing': return 'badge-orange'
    case 'stored': return 'badge-green'
    case 'skipped': return 'badge-muted'
    case 'poll_start':
    case 'poll_complete': return 'badge-purple'
    case 'error': return 'badge-red'
    default: return 'badge-muted'
  }
}

function ActivityFeed({ events, onClear }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [events])

  return (
    <div className="card" style={{ display: 'grid', gridTemplateRows: 'auto 1fr' }}>
      <div className="card-header">
        <div>
          <div className="card-title">
            <span className="pulse-dot pulse-dot--cyan" />
            <span>Activity Feed</span>
            <span className="badge badge-muted">{events.length}</span>
          </div>
          <div className="card-subtitle">Live SSE events from the backend</div>
        </div>
        <button className="btn" type="button" onClick={onClear}>Clear feed</button>
      </div>

      <div className="scroll-area">
        {events.length === 0 ? (
          <div className="feed-empty">
            <div>
              <div className="feed-empty__icon">📡</div>
              <div>Waiting for events…</div>
            </div>
          </div>
        ) : (
          <div>
            {events.map((event, index) => (
              <div key={`${event.type}-${index}-${event.timestamp || ''}`} className={`feed-item ${eventTone(event.type)}`}>
                <div className={`feed-item__icon ${eventColor(event.type)}`}>
                  {event.type === 'processing' ? <span className="spinner" style={{ width: 12, height: 12 }} /> : eventIcon(event.type)}
                </div>
                <div className="feed-item__content">
                  <div className="feed-item__label">{event.type.replace(/_/g, ' ')}</div>
                  <div className="feed-item__path">{event.path || event.file_name || event.message || '—'}</div>
                </div>
                <div className="feed-item__time">{formatTime(event.timestamp)}</div>
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </div>
    </div>
  )
}

function DetailItem({ label, value }) {
  return (
    <div>
      <div className="detail-item__label">{label}</div>
      <div className="detail-item__value">{value ?? '—'}</div>
    </div>
  )
}

export default function Dashboard({ user, rootFolder, onChangeFolder, onLogout }) {
  const [files, setFiles] = useState([])
  const [events, setEvents] = useState([])
  const [loadingFiles, setLoadingFiles] = useState(true)
  const [pollingEnabled, setPollingEnabled] = useState(true)
  const [isCrawling, setIsCrawling] = useState(false)
  const [secondsLeft, setSecondsLeft] = useState(30)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [sortKey, setSortKey] = useState('folder_number')
  const [expanded, setExpanded] = useState({})
  const [now, setNow] = useState(Date.now())

  const eventSourceRef = useRef(null)
  const reconnectTimerRef = useRef(null)
  const aliveRef = useRef(true)

  useEffect(() => {
    void bootstrap()
    aliveRef.current = true
    return () => {
      aliveRef.current = false
      eventSourceRef.current?.close()
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
    }
  }, [])

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    if (!pollingEnabled) return
    const t = setInterval(() => {
      setSecondsLeft((prev) => (prev > 0 ? prev - 1 : 0))
    }, 1000)
    return () => clearInterval(t)
  }, [pollingEnabled])

  async function bootstrap() {
    try {
      const status = await fetchJSON('/api/status')
      setPollingEnabled(!!status.polling)
      setSecondsLeft(status.polling ? 30 : 0)
      await loadFiles(false)
      connectSSE()
    } catch {
      await loadFiles(false)
      connectSSE()
    }
  }

  async function loadFiles(markNew = false) {
    try {
      setLoadingFiles(true)
      const data = await fetchJSON('/api/files')
      const incoming = Array.isArray(data.files) ? data.files : []
      setFiles((prev) => mergeFiles(prev, incoming, markNew))
    } catch {
      // keep current files
    } finally {
      setLoadingFiles(false)
    }
  }

  function mergeFiles(prev, incoming, markNew) {
    const map = new Map(prev.map((item) => [item.source_id, item]))
    for (const item of incoming) {
      const existing = map.get(item.source_id)
      if (existing) {
        map.set(item.source_id, { ...existing, ...item, __addedAt: existing.__addedAt || item.__addedAt || 0 })
      } else {
        map.set(item.source_id, { ...item, __addedAt: markNew ? Date.now() : 0 })
      }
    }

    const merged = Array.from(map.values())
    merged.sort((a, b) => {
      const left = Number(a.folder_number || 0)
      const right = Number(b.folder_number || 0)
      if (left !== right) return left - right
      return String(a.file_name || '').localeCompare(String(b.file_name || ''))
    })

    return merged
  }

  function pushEvent(event) {
    const normalized = { ...event, timestamp: event.timestamp || new Date().toISOString() }
    setEvents((prev) => [...prev, normalized].slice(-300))
  }

  function connectSSE() {
    if (eventSourceRef.current) return

    const source = new EventSource('/api/events')
    eventSourceRef.current = source

    source.onmessage = (message) => {
      let event
      try {
        event = JSON.parse(message.data)
      } catch {
        return
      }
      if (event.type === 'ping') return

      pushEvent(event)

      if (event.type === 'crawl_start' || event.type === 'poll_start') {
        setIsCrawling(true)
        setSecondsLeft(30)
      }
      if (event.type === 'poll_skip') {
        setIsCrawling(false)
      }
      if (event.type === 'stored') {
        setPollingEnabled(true)
      }
      if (event.type === 'crawl_complete' || event.type === 'poll_complete') {
        setIsCrawling(false)
        setSecondsLeft(30)
        void loadFiles(true)
      }
      if (event.type === 'error') {
        setIsCrawling(false)
      }
    }

    source.onerror = () => {
      source.close()
      eventSourceRef.current = null
      if (!aliveRef.current) return
      reconnectTimerRef.current = setTimeout(() => {
        if (aliveRef.current) connectSSE()
      }, 3000)
    }
  }

  async function handleStopPolling() {
    await fetchJSON('/api/stop-poll', { method: 'POST' })
    setPollingEnabled(false)
    setSecondsLeft(0)
  }

  async function handleStartPolling() {
    await fetchJSON('/api/start-poll', { method: 'POST' })
    setPollingEnabled(true)
    setSecondsLeft(30)
  }

  const visibleFiles = useMemo(() => {
    const q = search.trim().toLowerCase()
    const filtered = files.filter((file) => {
      const matchesText = !q || `${file.file_name || ''} ${file.path || ''}`.toLowerCase().includes(q)
      const matchesStatus = statusFilter === 'all' || file.content_status === statusFilter
      return matchesText && matchesStatus
    })

    filtered.sort((a, b) => {
      if (sortKey === 'folder_number') {
        return Number(a.folder_number || 0) - Number(b.folder_number || 0)
      }
      if (sortKey === 'name') {
        return String(a.file_name || '').localeCompare(String(b.file_name || ''))
      }
      if (sortKey === 'modified_at') {
        const left = new Date(a.modified_at || 0).getTime()
        const right = new Date(b.modified_at || 0).getTime()
        return left - right
      }
      return 0
    })

    return filtered
  }, [files, search, statusFilter, sortKey])

  function toggleExpanded(sourceId) {
    setExpanded((prev) => ({ ...prev, [sourceId]: !prev[sourceId] }))
  }

  const fileCount = files.length

  return (
    <div className="layout-grid">
      <header className="navbar">
        <div className="navbar__left">
          <div className="brand">
            <div className="brand__title">Drive Connector</div>
            <div className="brand__sub">{rootFolder?.name || 'No folder selected'}</div>
          </div>
          <span className="badge badge-muted nav-chip">📁 {rootFolder?.name || 'Root folder'}</span>
        </div>

        <div className="navbar__center" style={{ justifyContent: 'center', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span className={`pulse-dot ${isCrawling ? 'pulse-dot--orange' : 'pulse-dot--green'}`} />
            <span className="mono muted">{isCrawling ? 'syncing' : 'idle'}</span>
          </div>
          <span className="badge badge-muted">{fileCount} files stored</span>
          <span className="badge badge-purple">Next poll in {pollingEnabled ? secondsLeft : 'paused'}</span>
          {pollingEnabled ? (
            <button className="btn btn-danger" type="button" onClick={handleStopPolling}>⏹ Stop Polling</button>
          ) : (
            <button className="btn btn-success" type="button" onClick={handleStartPolling}>▶ Start Polling</button>
          )}
        </div>

        <div className="navbar__right" style={{ flexWrap: 'wrap' }}>
          {user ? (
            <div className="badge badge-muted" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              {user.picture ? (
                <img src={user.picture} alt={user.email || 'user'} style={{ width: 28, height: 28, borderRadius: 999 }} />
              ) : (
                <div className="file-icon" style={{ width: 28, height: 28 }}>👤</div>
              )}
              <div style={{ minWidth: 0 }}>
                <div className="mono" style={{ fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{user.email}</div>
                <div className="muted" style={{ fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{user.name || 'Signed in'}</div>
              </div>
            </div>
          ) : null}
          <button className="btn" type="button" onClick={onChangeFolder}>Change folder</button>
          <button className="btn" type="button" onClick={onLogout}>Logout</button>
        </div>
      </header>

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
                <div className="card-subtitle">Incremental append-only view of stored normalized documents</div>
              </div>

              <div className="files-toolbar" style={{ width: '100%' }}>
                <input className="input" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search by file name or path…" />
                <select className="select" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                  <option value="all">All statuses</option>
                  <option value="accessible">Accessible</option>
                  <option value="inaccessible">Inaccessible</option>
                  <option value="deleted">Deleted</option>
                  <option value="too_large">Too large</option>
                  <option value="error">Error</option>
                </select>
                <select className="select" value={sortKey} onChange={(e) => setSortKey(e.target.value)}>
                  <option value="folder_number">Sort: folder number</option>
                  <option value="name">Sort: name</option>
                  <option value="modified_at">Sort: modified date</option>
                </select>
                <div className="badge badge-muted">{loadingFiles ? 'Refreshing…' : 'Live'}</div>
              </div>
            </div>

            <div className="scroll-area">
              <table className="files-table">
                <thead>
                  <tr>
                    <th style={{ width: 72 }}>Type</th>
                    <th>File</th>
                    <th style={{ width: 110 }}>Badge</th>
                    <th style={{ width: 110 }}>Size</th>
                    <th style={{ width: 130 }}>Status</th>
                    <th style={{ width: 100 }}>Storage</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleFiles.length === 0 ? (
                    <tr>
                      <td colSpan={6} style={{ padding: 28 }}>
                        <div className="feed-empty" style={{ minHeight: 220 }}>
                          <div>
                            <div className="feed-empty__icon">🗂️</div>
                            <div>{loadingFiles ? 'Loading synced files…' : 'No synced files yet'}</div>
                          </div>
                        </div>
                      </td>
                    </tr>
                  ) : visibleFiles.map((file) => {
                    const expandedRow = !!expanded[file.source_id]
                    const isNew = file.__addedAt && now - file.__addedAt < 5000
                    return (
                      <Fragment key={file.source_id}>
                        <tr className={`file-row ${expandedRow ? 'file-row--expanded' : ''} ${isNew ? 'fade-in-up' : ''}`} onClick={() => toggleExpanded(file.source_id)}>
                          <td><div className="file-icon">{getFileIcon(file)}</div></td>
                          <td>
                            <div className="file-name">{file.file_name}</div>
                            <div className="file-path">{file.path}</div>
                          </td>
                          <td>
                            <span className="badge badge-muted">{getMimeBadge(file)}</span>
                            {isNew ? <div style={{ marginTop: 8 }}><span className="badge badge-cyan">NEW</span></div> : null}
                          </td>
                          <td>{formatSize(file.size_bytes)}</td>
                          <td><span className={`badge ${statusTone(file.content_status)}`}>{file.content_status || '—'}</span></td>
                          <td className="mono">#{file.folder_number ?? '—'}</td>
                        </tr>
                        {expandedRow ? (
                          <tr className="expand-row">
                            <td colSpan={6} className="expand-cell">
                              <div className="detail-grid">
                                <DetailItem label="source_id" value={file.source_id} />
                                <DetailItem label="source_type" value={file.source_type} />
                                <DetailItem label="owner_email" value={file.owner_email} />
                                <DetailItem label="modified_at" value={formatTime(file.modified_at)} />
                                <DetailItem label="connector_synced_at" value={formatTime(file.connector_synced_at)} />
                                <DetailItem label="shared" value={String(!!file.shared)} />
                                <DetailItem label="export_mime_type" value={file.export_mime_type || '—'} />
                                <DetailItem label="raw_file_path" value={file.raw_file_path || '—'} />
                                <DetailItem label="file_extension" value={file.file_extension || '—'} />
                                <DetailItem label="file_type" value={file.file_type || '—'} />
                                <DetailItem label="size_human" value={file.size_human || '—'} />
                                <DetailItem label="parent_folder_id" value={file.parent_folder_id || '—'} />
                                <DetailItem label="web_url" value={file.web_url || '—'} />
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
