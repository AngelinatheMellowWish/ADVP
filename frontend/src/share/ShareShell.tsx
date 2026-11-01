import { useEffect, type ReactNode } from 'react'

import type { SharePayload } from './types'
import '../styles.css'

export function ShareShell({
  payload,
  renderer,
  selectionId,
  title,
  children,
}: {
  payload: SharePayload
  renderer: string
  selectionId: string
  title: string
  children: ReactNode
}) {
  const render = payload.render ?? {}
  const selected = payload.selection?.selected ?? {}

  useEffect(() => {
    window.__ADVP_READY__ = true
  }, [])

  return (
    <main className="share-page">
      <header className="share-header">
        <p className="eyebrow">ADVP · 离线分享</p>
        <h1>{title}</h1>
        <p className="muted">
          {payload.dataset?.name ?? '数据集'} · {payload.dataset?.format ?? ''} · {renderer} ·{' '}
          {render.row_count ?? payload.dataset?.row_count ?? 0} 行
          {render.sampled ? '（采样）' : ''}
        </p>
        {selected.reason ? <p>{selected.reason}</p> : null}
        {selected.fields ? (
          <div className="chips">
            {Object.entries(selected.fields).map(([role, name]) => (
              <span className="chip" key={role}>
                {role}: {name}
              </span>
            ))}
          </div>
        ) : null}
      </header>
      <section className="share-figure" data-selection={selectionId}>
        {children}
      </section>
      <footer className="muted share-footer">
        ADVP 本地导出 · 不含 API Key 或完整敏感样本
      </footer>
    </main>
  )
}
