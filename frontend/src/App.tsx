import { useEffect, useState } from 'react'

import { fetchHealth, type Health } from './api/health'
import { DataWorkbench } from './components/DataWorkbench'
import { ProviderPanel } from './components/ProviderPanel'
import { ShutdownControl } from './components/ShutdownControl'

type LoadState = 'loading' | 'ok' | 'error'

export function App() {
  const [state, setState] = useState<LoadState>('loading')
  const [health, setHealth] = useState<Health | null>(null)

  useEffect(() => {
    let cancelled = false

    fetchHealth()
      .then((data) => {
        if (!cancelled) {
          setHealth(data)
          setState(data.status === 'ok' ? 'ok' : 'error')
        }
      })
      .catch(() => {
        if (!cancelled) {
          setState('error')
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  return (
    <main className="app">
      <ShutdownControl />
      <section className="hero">
        <p className="eyebrow">Automated Data Visualization Platform</p>
        <h1>ADVP</h1>
        <p className="lede">
          本地优先的 AI 数据可视化工作台。数据接入、画像、分析摘要、清洗、规则筛选、
          AI 选型、评分、管线状态机、2D/地图/网络/影像/3D 图表与报告已可用。
        </p>
        <div className="status" data-testid="backend-status">
          <span className={`dot ${state}`} />
          {state === 'loading' && '正在连接本地服务…'}
          {state === 'ok' && `后端正常 · v${health?.version ?? '?'}`}
          {state === 'error' && '后端未连接'}
        </div>
      </section>

      <section className="cards" aria-label="能力概览">
        <article>
          <h2>数据接入</h2>
          <p>表格、科学格式、影像、SQL、远程 URL 与实时流。</p>
        </article>
        <article>
          <h2>AI 管线</h2>
          <p>画像、分析摘要、清洗、规则筛选、AI 选型、七维评分、可暂停管线、追踪与报告。</p>
        </article>
        <article>
          <h2>科研 3D</h2>
          <p>浏览器交互与服务端体渲染，统一 Scene JSON。</p>
        </article>
      </section>

      <DataWorkbench />
      <ProviderPanel />

      <footer>
        <span>本地工作台 · v{health?.version ?? '?'}</span>
        <span>仅监听 127.0.0.1</span>
      </footer>
    </main>
  )
}
