export default function LoginPage({ onLogin, error }) {
  return (
    <div className="center-screen">
      <div className="panel glass" style={{ width: 'min(560px, 100%)', padding: 28 }}>
        <div style={{ display: 'grid', gap: 18 }}>
          <div>
            <div className="badge badge-cyan" style={{ marginBottom: 12 }}>INT Technologies</div>
            <h1 style={{ margin: 0, fontSize: 34, letterSpacing: '-0.03em' }}>Drive Connector</h1>
            <p className="muted" style={{ margin: '10px 0 0', lineHeight: 1.7 }}>
              Sign in with Google to select a root folder and start recursive Drive syncing.
            </p>
          </div>

          {error ? (
            <div className="badge badge-red" style={{ padding: '10px 12px', whiteSpace: 'normal', lineHeight: 1.5 }}>
              {error}
            </div>
          ) : null}

          <button className="btn btn-primary" onClick={onLogin} style={{ justifyContent: 'center', fontWeight: 700 }}>
            Sign in with Google
          </button>

          <div className="panel" style={{ padding: 16, background: 'rgba(255,255,255,0.02)' }}>
            <div className="mono muted" style={{ fontSize: 12, marginBottom: 8 }}>OAuth scopes</div>
            <div style={{ display: 'grid', gap: 8 }}>
              <div className="badge badge-muted">drive.readonly</div>
              <div className="badge badge-muted">drive.metadata.readonly</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
