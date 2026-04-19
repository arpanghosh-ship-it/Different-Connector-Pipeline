export default function LoginPage({ onGoogleLogin, onDropboxLogin, error }) {
  return (
    <div className="center-screen">
      <div className="panel glass" style={{ width: 'min(560px, 100%)', padding: 28 }}>
        <div style={{ display: 'grid', gap: 18 }}>

          <div>
            <div className="badge badge-cyan" style={{ marginBottom: 12 }}>INT Technologies</div>
            <h1 style={{ margin: 0, fontSize: 34, letterSpacing: '-0.03em' }}>Connector Pipeline</h1>
            <p className="muted" style={{ margin: '10px 0 0', lineHeight: 1.7 }}>
              Connect a cloud storage provider to start recursive syncing with real-time change detection.
            </p>
          </div>

          {error ? (
            <div className="badge badge-red" style={{ padding: '10px 12px', whiteSpace: 'normal', lineHeight: 1.5 }}>
              {error}
            </div>
          ) : null}

          {/* ── Google Drive ── */}
          <div className="panel" style={{ padding: 20, background: 'rgba(255,255,255,0.03)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
              <div style={{ fontSize: 24 }}>📁</div>
              <div>
                <div style={{ fontWeight: 700, fontSize: 16 }}>Google Drive</div>
                <div className="muted" style={{ fontSize: 12 }}>OAuth 2.0 · drive.readonly scope</div>
              </div>
            </div>
            <button
              className="btn btn-primary"
              onClick={onGoogleLogin}
              style={{ width: '100%', justifyContent: 'center', fontWeight: 700 }}
            >
              Sign in with Google
            </button>
            <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
              <div className="badge badge-muted">drive.readonly</div>
              <div className="badge badge-muted">drive.metadata.readonly</div>
              <div className="badge badge-muted">Webhook push notifications</div>
            </div>
          </div>

          {/* ── Dropbox ── */}
          <div className="panel" style={{ padding: 20, background: 'rgba(255,255,255,0.03)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
              <div style={{ fontSize: 24 }}>📦</div>
              <div>
                <div style={{ fontWeight: 700, fontSize: 16 }}>Dropbox</div>
                <div className="muted" style={{ fontSize: 12 }}>OAuth 2.0 · files.content.read scope</div>
              </div>
            </div>
            <button
              className="btn"
              onClick={onDropboxLogin}
              style={{
                width: '100%',
                justifyContent: 'center',
                fontWeight: 700,
                background: '#0061FF',
                color: '#fff',
                border: 'none',
              }}
            >
              Sign in with Dropbox
            </button>
            <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
              <div className="badge badge-muted">files.content.read</div>
              <div className="badge badge-muted">files.metadata.read</div>
              <div className="badge badge-muted">Webhook push notifications</div>
            </div>
          </div>

          {/* ── SharePoint (coming soon) ── */}
          <div className="panel" style={{ padding: 20, background: 'rgba(255,255,255,0.02)', opacity: 0.5 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
              <div style={{ fontSize: 24 }}>🗂</div>
              <div>
                <div style={{ fontWeight: 700, fontSize: 16 }}>
                  SharePoint
                  <span className="badge badge-muted" style={{ fontSize: 10, marginLeft: 8 }}>Coming soon</span>
                </div>
                <div className="muted" style={{ fontSize: 12 }}>Microsoft OAuth 2.0 · Graph API</div>
              </div>
            </div>
            <button
              className="btn"
              disabled
              style={{ width: '100%', justifyContent: 'center', fontWeight: 700, cursor: 'not-allowed' }}
            >
              Sign in with Microsoft (coming soon)
            </button>
          </div>

        </div>
      </div>
    </div>
  )
}
