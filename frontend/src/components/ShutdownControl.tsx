import { useEffect, useState } from 'react'

import {
  getLifecycle,
  shutdownService,
  type LifecycleState,
} from '../api/lifecycle'
import { errorMessage } from '../api/projects'

type Modal = 'confirm' | 'warning' | null

export function ShutdownControl() {
  const [lifecycle, setLifecycle] = useState<LifecycleState | null>(null)
  const [modal, setModal] = useState<Modal>(null)
  const [busy, setBusy] = useState(false)
  const [closed, setClosed] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    getLifecycle()
      .then((state) => {
        if (!cancelled) setLifecycle(state)
      })
      .catch(() => {
        if (!cancelled) setLifecycle(null)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!lifecycle?.shutdown_enabled || closed) return
    const handler = (event: BeforeUnloadEvent) => {
      const message = '关闭页面不会停止 ADVP 本地服务；如需释放资源，请先点击“关闭本地服务”。'
      event.preventDefault()
      event.returnValue = message
      return message
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [lifecycle, closed])

  async function open() {
    setError(null)
    try {
      const state = await getLifecycle()
      setLifecycle(state)
      if (!state.shutdown_enabled) return
      setModal(state.active_tasks.total > 0 ? 'warning' : 'confirm')
    } catch (caught) {
      setError(errorMessage(caught))
    }
  }

  async function confirm(force: boolean) {
    setBusy(true)
    setError(null)
    try {
      await shutdownService(force)
      setModal(null)
      setClosed(true)
    } catch (caught) {
      setError(errorMessage(caught))
      try {
        const state = await getLifecycle()
        setLifecycle(state)
        setModal(state.active_tasks.total > 0 ? 'warning' : 'confirm')
      } catch {
        setModal(null)
      }
    } finally {
      setBusy(false)
    }
  }

  if (closed) {
    return (
      <div className="shutdown-overlay" role="status">
        <div className="shutdown-modal">
          <h2>服务已关闭</h2>
          <p>ADVP 本地后端已停止，可关闭此页面。</p>
          <p className="muted">工程与数据仍保存在 `%USERPROFILE%\.advp`。</p>
        </div>
      </div>
    )
  }

  if (!lifecycle?.shutdown_enabled) return null

  const tasks = lifecycle.active_tasks

  return (
    <>
      <div className="app-lifecycle">
        <button className="button danger" type="button" onClick={() => void open()}>
          关闭本地服务
        </button>
      </div>
      {error ? (
        <p className="error app-lifecycle-error" role="alert">
          {error}
        </p>
      ) : null}
      {modal ? (
        <div className="shutdown-backdrop">
          <div className="shutdown-modal" role="dialog" aria-modal="true">
            {modal === 'warning' ? (
              <>
                <h2>仍有 {tasks.total} 个任务在运行</h2>
                <p>关闭会中断以下任务，未落盘的状态可能丢失：</p>
                <ul className="shutdown-counts">
                  <li>管线：{tasks.pipelines}</li>
                  <li>导出：{tasks.exports}</li>
                  <li>3D 渲染：{tasks.render_jobs}</li>
                  <li>实时流：{tasks.live_streams}</li>
                </ul>
                <div className="shutdown-actions">
                  <button
                    className="button ghost"
                    type="button"
                    disabled={busy}
                    onClick={() => setModal(null)}
                  >
                    取消
                  </button>
                  <button
                    className="button danger"
                    type="button"
                    disabled={busy}
                    onClick={() => void confirm(true)}
                  >
                    仍然关闭
                  </button>
                </div>
              </>
            ) : (
              <>
                <h2>关闭 ADVP 本地服务？</h2>
                <p>关闭后将停止后端进程；工程与已有数据会保留。</p>
                <p className="muted">
                  关闭浏览器页面不会停止服务，此操作才会释放本地资源。
                </p>
                <div className="shutdown-actions">
                  <button
                    className="button ghost"
                    type="button"
                    disabled={busy}
                    onClick={() => setModal(null)}
                  >
                    取消
                  </button>
                  <button
                    className="button danger"
                    type="button"
                    disabled={busy}
                    onClick={() => void confirm(false)}
                  >
                    关闭服务
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      ) : null}
    </>
  )
}
