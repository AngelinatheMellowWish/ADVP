import { useState } from 'react'

import { errorMessage } from '../api/projects'
import { startTrame, stopTrame, type TrameSession } from '../api/trame3d'

export function SciViewPanel({ sceneId }: { sceneId: string }) {
  const [session, setSession] = useState<TrameSession | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function start() {
    setBusy(true)
    setError(null)
    try {
      setSession(await startTrame(sceneId))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function stop() {
    if (!session) return
    setBusy(true)
    try {
      await stopTrame(session.id)
      setSession(null)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="sciview-panel">
      <div className="inline-form">
        <button className="button" onClick={start} disabled={busy || session !== null}>
          {busy && !session ? '启动中…' : '启动 trame SciView'}
        </button>
        {session ? (
          <button className="button" onClick={stop} disabled={busy}>
            停止会话
          </button>
        ) : null}
        <span className="muted">
          {session ? `本机会话 ${session.id.slice(0, 8)} · 端口 ${session.port}` : '仅本机回环'}
        </span>
      </div>
      {error ? <p className="error">{error}</p> : null}
      {session ? (
        <iframe
          className="sciview-frame"
          title="ADVP SciView"
          src={session.url}
          sandbox="allow-scripts allow-same-origin allow-forms"
        />
      ) : null}
    </div>
  )
}
