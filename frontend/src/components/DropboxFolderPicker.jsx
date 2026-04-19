import { useEffect, useState } from 'react'

async function fetchJSON(url, options) {
  const response = await fetch(url, options)
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(data?.detail || data?.message || response.statusText || 'Request failed')
  }
  return data
}

function FolderSkeleton() {
  return (
    <div className="tree-node" style={{ padding: 12 }}>
      <div style={{ display: 'grid', gap: 10 }}>
        <div className="skeleton" style={{ height: 16, width: '42%' }} />
        <div className="skeleton" style={{ height: 36, width: '100%' }} />
        <div className="skeleton" style={{ height: 36, width: '100%' }} />
      </div>
    </div>
  )
}

function FolderNode({ node, depth, childrenMap, openMap, loadingMap, onToggle, onSelect }) {
  const isOpen   = !!openMap[node.id]
  const children = childrenMap[node.id] || []

  return (
    <div className="tree-node fade-in-up" style={{ marginLeft: depth ? 14 : 0 }}>
      <div className="tree-node__row">
        <button
          className={`tree-node__toggle ${isOpen ? 'is-open' : ''}`}
          onClick={() => onToggle(node)}
          type="button"
        >▶</button>
        <div>{isOpen ? '📂' : '📦'}</div>
        <div className="tree-node__name">{node.name}</div>
        <button className="btn btn-primary" type="button" onClick={() => onSelect(node)}>
          Select
        </button>
      </div>

      {isOpen ? (
        <div className="tree-node__children">
          {loadingMap[node.id] ? (
            <div className="badge badge-muted">Loading subfolders…</div>
          ) : children.length ? (
            children.map((child) => (
              <div key={child.id} className="tree-node__child">
                <FolderNode
                  node={child}
                  depth={depth + 1}
                  childrenMap={childrenMap}
                  openMap={openMap}
                  loadingMap={loadingMap}
                  onToggle={onToggle}
                  onSelect={onSelect}
                />
              </div>
            ))
          ) : (
            <div className="badge badge-muted">No subfolders</div>
          )}
        </div>
      ) : null}
    </div>
  )
}

export default function DropboxFolderPicker({ user, onBack, onSelectFolder }) {
  const [rootFolders, setRootFolders] = useState([])
  const [childrenMap, setChildrenMap] = useState({})
  const [openMap,     setOpenMap]     = useState({})
  const [loadingMap,  setLoadingMap]  = useState({ root: true })
  const [error,       setError]       = useState('')
  const [selectedId,  setSelectedId]  = useState('')

  useEffect(() => {
    void loadChildren('', true)   // '' = Dropbox account root
  }, [])

  async function loadChildren(parentPath, isRoot = false) {
    const key = parentPath || 'root'
    try {
      setLoadingMap((prev) => ({ ...prev, [key]: true }))
      const data    = await fetchJSON(`/api/dropbox/folders?path=${encodeURIComponent(parentPath)}`)
      const folders = (data.folders || []).map((f) => ({ id: f.path, name: f.name, path: f.path }))
      if (isRoot) setRootFolders(folders)
      else        setChildrenMap((prev) => ({ ...prev, [parentPath]: folders }))
      setError('')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoadingMap((prev) => ({ ...prev, [key]: false }))
    }
  }

  async function handleToggle(node) {
    const isOpen = !!openMap[node.id]
    setOpenMap((prev) => ({ ...prev, [node.id]: !isOpen }))
    if (!isOpen && !childrenMap[node.id] && !loadingMap[node.id]) {
      await loadChildren(node.id, false)
    }
  }

  async function handleSelect(node) {
    setSelectedId(node.id)
    await onSelectFolder({ id: node.id, name: node.name })
  }

  return (
    <div className="app-shell">
      <div style={{ position: 'fixed', top: 18, left: 18, zIndex: 10 }}>
        <button className="btn" type="button" onClick={onBack}>← Back</button>
      </div>

      <div className="center-screen" style={{ paddingTop: 72 }}>
        <div className="panel glass" style={{ width: 'min(1060px, 100%)', padding: 24 }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, marginBottom: 20, flexWrap: 'wrap' }}>
            <div>
              <div className="badge badge-cyan" style={{ marginBottom: 10 }}>
                📦 Dropbox — Step 2 of 2
              </div>
              <h2 style={{ margin: 0, fontSize: 28, letterSpacing: '-0.03em' }}>
                Select a root folder
              </h2>
              <p className="muted" style={{ margin: '10px 0 0' }}>
                Choose the Dropbox folder to crawl recursively. All files inside will be synced in real-time.
              </p>
            </div>

            {user ? (
              <div className="badge badge-muted" style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px' }}>
                <div className="file-icon" style={{ width: 28, height: 28 }}>📦</div>
                <div style={{ minWidth: 0 }}>
                  <div className="mono" style={{ fontSize: 12 }}>{user.email}</div>
                  <div className="muted" style={{ fontSize: 11 }}>{user.name || 'Dropbox'}</div>
                </div>
              </div>
            ) : null}
          </div>

          {error ? (
            <div className="badge badge-red" style={{ marginBottom: 16, whiteSpace: 'normal' }}>
              {error}
            </div>
          ) : null}

          <div className="tree">
            {loadingMap.root ? (
              <FolderSkeleton />
            ) : rootFolders.length ? (
              rootFolders.map((folder) => (
                <FolderNode
                  key={folder.id}
                  node={folder}
                  depth={0}
                  childrenMap={childrenMap}
                  openMap={openMap}
                  loadingMap={loadingMap}
                  onToggle={handleToggle}
                  onSelect={handleSelect}
                />
              ))
            ) : (
              <div className="feed-empty">
                <div>
                  <div className="feed-empty__icon">📦</div>
                  <div>No folders found in your Dropbox</div>
                </div>
              </div>
            )}
          </div>

          {selectedId ? (
            <div className="badge badge-green" style={{ marginTop: 16 }}>
              ✓ Folder selected — Dropbox crawl started.
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}
