import { useState } from 'react'

import { errorMessage } from '../api/projects'
import {
  createScene,
  getGeometry,
  patchScene,
  type GeometryPayload,
  type SceneDocument,
  type SceneRecord,
} from '../api/scenes'
import { RenderPanel } from './RenderPanel'
import { SciViewPanel } from './SciViewPanel'
import { VtkScene } from './VtkScene'

const TABLE_MODES = ['points', 'surface']
const ARRAY_MODES = ['slice', 'isosurface', 'volume']

export function ScenePanel({
  datasetId,
  datasetKind,
}: {
  datasetId: string
  datasetKind: string
}) {
  const [scene, setScene] = useState<SceneRecord | null>(null)
  const [geometry, setGeometry] = useState<GeometryPayload | null>(null)
  const [mode, setMode] = useState(datasetKind === 'array' ? 'slice' : 'points')
  const [axis, setAxis] = useState(0)
  const [index, setIndex] = useState(0)
  const [colormap, setColormap] = useState('viridis')
  const [isovalue, setIsovalue] = useState(0.5)
  const [clipping, setClipping] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const modes = datasetKind === 'array' ? ARRAY_MODES : TABLE_MODES

  function defaultScene(): Record<string, unknown> {
    return {
      version: '1.0',
      data: { datasetId, fields: [], coordinates: {} },
      geometry: {
        type: mode,
        axis: datasetKind === 'array' ? axis : undefined,
        index: datasetKind === 'array' ? index : undefined,
      },
      colormap: { name: colormap, range: [0, 1], nanColor: '#808080' },
      backend: 'auto',
    }
  }

  async function create() {
    setBusy(true)
    setError(null)
    try {
      const record = await createScene(datasetId, defaultScene())
      setScene(record)
      await loadGeometry(record)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function updateScene() {
    if (!scene) return
    setBusy(true)
    setError(null)
    try {
      const record = await patchScene(scene.id, defaultScene())
      setScene(record)
      await loadGeometry(record)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function loadGeometry(record: SceneRecord) {
    const document = record.scene as SceneDocument
    setGeometry(
      await getGeometry(datasetId, {
        mode: document.geometry.type,
        axis: document.geometry.axis ?? 0,
        index: document.geometry.index ?? 0,
      }),
    )
  }

  async function reloadGeometry() {
    if (!scene) return
    setBusy(true)
    setError(null)
    try {
      await loadGeometry(scene)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="scene-panel" aria-label="3D 场景" data-testid="scene-panel">
      <div className="panel-title">
        <div>
          <h4>3D 场景 <span className="badge">Scene JSON v1</span></h4>
          <p className="muted">
            浏览器 VTK.js 渲染点云/切片/等值面；体渲染可切换服务端 Mayavi。
          </p>
        </div>
        <button className="button" onClick={create} disabled={busy}>
          {busy ? '处理中…' : '创建并加载'}
        </button>
      </div>

      <div className="chart-selection-controls">
        <label>
          几何
          <select value={mode} onChange={(event) => setMode(event.target.value)}>
            {modes.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        {datasetKind === 'array' ? (
          <>
            <label>
              轴
              <input
                type="number"
                min="0"
                max="3"
                value={axis}
                onChange={(event) => setAxis(Number(event.target.value))}
              />
            </label>
            <label>
              切片索引
              <input
                type="number"
                min="0"
                value={index}
                onChange={(event) => setIndex(Number(event.target.value))}
              />
            </label>
          </>
        ) : null}
        <label>
          色标
          <select value={colormap} onChange={(event) => setColormap(event.target.value)}>
            <option value="viridis">Viridis</option>
            <option value="grayscale">灰度</option>
            <option value="hot">Hot</option>
            <option value="jet">Jet</option>
          </select>
        </label>
        {mode === 'isosurface' ? (
          <label>
            等值
            <input
              type="range"
              min="0"
              max="1"
              step="0.01"
              value={isovalue}
              onChange={(event) => setIsovalue(Number(event.target.value))}
            />
            <span className="muted">{isovalue.toFixed(2)}</span>
          </label>
        ) : null}
        <label className="inline-check">
          <input
            type="checkbox"
            checked={clipping}
            onChange={(event) => setClipping(event.target.checked)}
          />
          裁剪（服务端）
        </label>
        <button className="button" onClick={updateScene} disabled={busy || !scene}>
          更新场景
        </button>
        <button className="button" onClick={reloadGeometry} disabled={busy || !scene}>
          重新加载几何
        </button>
      </div>

      {scene ? (
        <p className="muted">
          scene {scene.id} · {scene.version} · hash {scene.scene_hash.slice(0, 12)}…
        </p>
      ) : null}
      {scene ? (
        <div className="inline-form">
          <a className="button" href={`/api/scenes/${scene.id}/export/python`}>
            导出 Python
          </a>
          <a className="button" href={`/api/scenes/${scene.id}/export/json`}>
            导出 Scene JSON
          </a>
        </div>
      ) : null}
      {geometry?.sampled ? (
        <p className="notice">
          已降采样：LOD {geometry.lod ?? 1}，显示形状{' '}
          {geometry.display_shape?.join(' × ') ?? '—'}
        </p>
      ) : null}
      {error ? <p className="error">{error}</p> : null}
      {geometry ? (
        <VtkScene
          geometry={geometry}
          colormap={colormap}
          isovalue={isovalue}
          clipping={clipping}
        />
      ) : (
        <p className="muted">创建场景后加载 3D 几何。</p>
      )}
      {scene ? <RenderPanel sceneId={scene.id} /> : null}
      {scene ? <SciViewPanel sceneId={scene.id} /> : null}
    </section>
  )
}
