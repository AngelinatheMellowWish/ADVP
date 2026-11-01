import { useEffect, useState } from 'react'

import { errorMessage } from '../api/projects'
import {
  cancelRenderJob,
  createRender,
  getRenderJob,
  probeRenderer,
  renderDownloadUrl,
  type RenderJob,
  type RendererProbe,
} from '../api/render3d'

export function RenderPanel({
  sceneId,
  mode,
  isovalue,
  animation,
}: {
  sceneId: string
  mode?: string
  isovalue?: number
  animation?: Record<string, unknown>
}) {
  const [probe, setProbe] = useState<RendererProbe | null>(null)
  const [job, setJob] = useState<RenderJob | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    probeRenderer()
      .then((result) => {
        if (!cancelled) setProbe(result)
      })
      .catch(() => {
        if (!cancelled) setProbe(null)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!job || (job.status !== 'pending' && job.status !== 'running')) return
    const timer = window.setInterval(() => {
      getRenderJob(job.id)
        .then(setJob)
        .catch((err: unknown) => setError(errorMessage(err)))
    }, 1000)
    return () => window.clearInterval(timer)
  }, [job])

  async function start() {
    setBusy(true)
    setError(null)
    try {
      setJob(
        await createRender(sceneId, {
          width: 1280,
          height: 720,
          mode,
          isovalue,
          animation,
        }),
      )
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function cancel() {
    if (!job) return
    setBusy(true)
    try {
      setJob(await cancelRenderJob(job.id))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="render-panel">
      <div className="inline-form">
        <button className="button" onClick={start} disabled={busy}>
          {busy ? '提交中…' : '服务端渲染 PNG'}
        </button>
        {job && (job.status === 'pending' || job.status === 'running') ? (
          <button className="button" onClick={cancel} disabled={busy}>
            取消
          </button>
        ) : null}
        {job?.status === 'succeeded' ? (
          <a className="button" href={renderDownloadUrl(job.id)}>
            下载 PNG
          </a>
        ) : null}
      </div>
      {probe ? (
        <p className="muted">
          渲染环境：VTK {probe.vtk} · Mayavi {probe.mayavi} ·{' '}
          {probe.software_rendering ? '软件渲染' : probe.gl_renderer ?? 'GPU'}
          {probe.trame ? ' · trame 可用' : ''}
        </p>
      ) : (
        <p className="muted">未检测到独立 3D 渲染环境；请设置 ADVP_RENDER_PYTHON。</p>
      )}
      {job ? (
        <p className={job.status === 'failed' ? 'error' : 'muted'}>
          渲染任务 {job.id.slice(0, 8)} · {job.status} · {job.progress}%
          {job.error ? ` · ${job.error}` : ''}
        </p>
      ) : null}
      {error ? <p className="error">{error}</p> : null}
    </div>
  )
}
