import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams, useSearchParams } from 'react-router-dom'

import { errorMessage, getDataset, type DatasetDetail } from '../api/projects'
import { probeRenderer, type RendererProbe } from '../api/render3d'
import {
  createScene,
  getGeometry,
  getScene,
  patchScene,
  type GeometryPayload,
  type SceneRecord,
  type SceneTransferFunction,
} from '../api/scenes'
import { useProject } from '../app/projectContext'
import { RenderPanel } from '../components/RenderPanel'
import { SciViewPanel } from '../components/SciViewPanel'
import { TransferFunctionEditor } from '../components/TransferFunctionEditor'
import { VtkScene } from '../components/VtkScene'
import {
  defaultTransferFunction,
  normalizeTransferFunction,
  sortTransferFunction,
} from '../state/transferFunction'

type SceneMode = 'points' | 'surface' | 'slice' | 'isosurface' | 'volume'
type Backend = 'auto' | 'webgl' | 'mayavi' | 'trame'
type Annotation = { text: string; position: number[]; color: string }

const TABLE_MODES: SceneMode[] = ['points', 'surface']
const ARRAY_MODES: SceneMode[] = ['slice', 'isosurface', 'volume']
const BACKENDS: Backend[] = ['auto', 'webgl', 'mayavi', 'trame']
const COLORMAPS = ['viridis', 'grayscale', 'hot', 'jet']

function datasetFields(dataset: DatasetDetail): string[] {
  if (dataset.kind === 'array') {
    const variable = dataset.schema_definition.variable
    return variable ? [variable] : []
  }
  return dataset.schema_definition.columns.map((column) => column.name)
}

function histogram(geometry: GeometryPayload | null, bins = 32): number[] {
  if (!geometry) return []
  const raw = geometry.values
  if (!raw) return []
  const values = (
    Array.isArray(raw[0])
      ? (raw as (number | null)[][]).flat()
      : (raw as (number | null)[])
  )
    .filter((value): value is number => typeof value === 'number' && Number.isFinite(value))
  if (values.length === 0) return []
  const [min, max] = geometry.range ?? [Math.min(...values), Math.max(...values)]
  const low = min ?? Math.min(...values)
  const high = max ?? Math.max(...values)
  const span = high > low ? high - low : 1
  const counts = Array.from({ length: bins }, () => 0)
  for (const value of values) {
    const index = Math.min(bins - 1, Math.max(0, Math.floor(((value - low) / span) * bins)))
    counts[index] += 1
  }
  return counts
}

export function P06Scene() {
  const { t } = useTranslation()
  const { projectId } = useParams<{ projectId?: string }>()
  const { project } = useProject()
  const [params, setParams] = useSearchParams()
  const datasetId = params.get('dataset') ?? project?.datasets[0]?.id ?? null
  const sceneParam = params.get('scene')

  const [dataset, setDataset] = useState<DatasetDetail | null>(null)
  const [probe, setProbe] = useState<RendererProbe | null>(null)
  const [scene, setScene] = useState<SceneRecord | null>(null)
  const [geometry, setGeometry] = useState<GeometryPayload | null>(null)
  const [mode, setMode] = useState<SceneMode>('points')
  const [axis, setAxis] = useState(0)
  const [index, setIndex] = useState(0)
  const [isovalue, setIsovalue] = useState(0.5)
  const [colormap, setColormap] = useState('viridis')
  const [backend, setBackend] = useState<Backend>('auto')
  const [transfer, setTransfer] = useState<SceneTransferFunction>(defaultTransferFunction())
  const [clippingEnabled, setClippingEnabled] = useState(false)
  const [planeOrigin, setPlaneOrigin] = useState<number[]>([0, 0, 0])
  const [planeNormal, setPlaneNormal] = useState<number[]>([1, 0, 0])
  const [ambient, setAmbient] = useState(0.2)
  const [diffuse, setDiffuse] = useState(0.8)
  const [annotations, setAnnotations] = useState<Annotation[]>([])
  const [frames, setFrames] = useState(1)
  const [fps, setFps] = useState(30)
  const [startFrame, setStartFrame] = useState(0)
  const [screenshot, setScreenshot] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!datasetId) {
      setDataset(null)
      return
    }
    let cancelled = false
    setLoading(true)
    getDataset(datasetId)
      .then((value) => {
        if (cancelled) return
        setDataset(value)
        setMode(value.kind === 'array' ? 'slice' : 'points')
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(errorMessage(caught))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [datasetId])

  useEffect(() => {
    let cancelled = false
    probeRenderer()
      .then((value) => {
        if (!cancelled) setProbe(value)
      })
      .catch(() => {
        if (!cancelled) setProbe(null)
      })
    return () => {
      cancelled = true
    }
  }, [])

  function applyScene(record: SceneRecord) {
    const document = record.scene
    setScene(record)
    setMode(document.geometry.type as SceneMode)
    setAxis(document.geometry.axis ?? 0)
    setIndex(document.geometry.index ?? 0)
    setColormap(document.colormap.name)
    setBackend(document.backend)
    setTransfer(normalizeTransferFunction(document.transferFunction))
    setClippingEnabled(document.clipping.enabled)
    const plane = document.clipping.planes[0]
    if (plane) {
      setPlaneOrigin(
        Array.isArray(plane.origin)
          ? (plane.origin as number[])
          : Array.isArray(plane.position)
            ? (plane.position as number[])
            : [0, 0, 0],
      )
      setPlaneNormal(Array.isArray(plane.normal) ? (plane.normal as number[]) : [1, 0, 0])
    }
    setAmbient(document.lighting.ambient)
    setDiffuse(document.lighting.diffuse)
    setAnnotations(
      document.annotations.map((item) => ({
        text: item.text,
        position: item.position,
        color: item.color ?? '#ffffff',
      })),
    )
    setFrames(document.animation.frames)
    setFps(document.animation.fps)
    setStartFrame(document.animation.startFrame ?? 0)
  }

  useEffect(() => {
    if (!sceneParam) return
    let cancelled = false
    getScene(sceneParam)
      .then(async (record) => {
        if (cancelled) return
        applyScene(record)
        setGeometry(
          await getGeometry(record.dataset_id, {
            mode: record.scene.geometry.type,
            axis: record.scene.geometry.axis ?? 0,
            index: record.scene.geometry.index ?? 0,
          }),
        )
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(errorMessage(caught))
      })
    return () => {
      cancelled = true
    }
  }, [sceneParam])

  const modes = dataset?.kind === 'array' ? ARRAY_MODES : TABLE_MODES
  const bins = useMemo(() => histogram(geometry), [geometry])

  function payload(): Record<string, unknown> {
    if (!dataset) return {}
    const existing = scene?.scene
    return {
      version: '1.1',
      data: {
        datasetId: dataset.id,
        fields: datasetFields(dataset),
        coordinates: existing?.data.coordinates ?? {},
      },
      geometry: {
        type: mode,
        axis: mode === 'slice' ? axis : undefined,
        index: mode === 'slice' ? index : undefined,
      },
      camera: existing?.camera,
      lighting: { ambient, diffuse },
      colormap: {
        name: colormap,
        range: existing?.colormap.range ?? [0, 1],
        nanColor: existing?.colormap.nanColor ?? '#808080',
      },
      transferFunction: sortTransferFunction(transfer),
      clipping: {
        enabled: clippingEnabled,
        planes: clippingEnabled ? [{ origin: planeOrigin, normal: planeNormal }] : [],
      },
      annotations: annotations.filter((item) => item.text.trim()),
      animation: {
        frames,
        fps,
        startFrame,
        resolution: existing?.animation.resolution ?? [1280, 720],
        cameraPath: existing?.animation.cameraPath ?? [],
      },
      backend,
      sampling: existing?.sampling ?? { maxElements: 50_000_000, mode: 'stride' },
      scientific: existing?.scientific ?? {
        coordinateReference: null,
        units: null,
        dataRange: null,
      },
    }
  }

  async function loadGeometry(record: SceneRecord) {
    setGeometry(
      await getGeometry(record.dataset_id, {
        mode: record.scene.geometry.type,
        axis: record.scene.geometry.axis ?? 0,
        index: record.scene.geometry.index ?? 0,
      }),
    )
  }

  async function saveScene() {
    if (!dataset) return
    setBusy(true)
    setError(null)
    setSaved(false)
    try {
      const record = scene
        ? await patchScene(scene.id, payload())
        : await createScene(dataset.id, payload())
      applyScene(record)
      const next = new URLSearchParams(params)
      next.set('dataset', dataset.id)
      next.set('scene', record.id)
      setParams(next)
      await loadGeometry(record)
      setSaved(true)
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  if (!datasetId) {
    return (
      <section className="page scene-page" data-testid="page-p06">
        <h1>{t('scenePage.title')}</h1>
        <p className="muted">{t('scenePage.missingDataset')}</p>
        {project && project.datasets.length > 0 ? (
          <ul className="file-list">
            {project.datasets.map((item) => (
              <li key={item.id}>
                <span>{item.name}</span>
                <Link className="btn" to={`/projects/${projectId}/scene?dataset=${item.id}`}>
                  {t('scenePage.selectDataset')}
                </Link>
              </li>
            ))}
          </ul>
        ) : null}
      </section>
    )
  }

  const serverDisabled = probe === null

  return (
    <section className="page scene-page" data-testid="page-p06">
      <header className="import-head">
        <div>
          <h1>{dataset?.name ?? t('scenePage.title')}</h1>
          <p className="muted">
            {t('scenePage.sceneVersion')} · {scene ? scene.scene_hash.slice(0, 12) : '—'}
          </p>
        </div>
        <Link className="btn" to={`/projects/${projectId}/pipeline?dataset=${datasetId}`}>
          {t('scenePage.backToPipeline')}
        </Link>
      </header>

      {error ? (
        <p className="error-text" role="alert">
          {error}
        </p>
      ) : null}
      {loading ? <p className="muted">{t('scenePage.loading')}</p> : null}
      {serverDisabled ? <p className="notice">{t('scenePage.probeUnavailable')}</p> : null}

      <div className="scene-layout">
        <div className="scene-main">
          <section className="card">
            <div className="panel-title">
              <div>
                <h2>{t('scenePage.geometry')}</h2>
                <p className="muted">{t('scenePage.geometryHint')}</p>
              </div>
              <button
                className="btn home-primary"
                type="button"
                onClick={() => void saveScene()}
                disabled={busy || !dataset}
              >
                {busy
                  ? t('scenePage.saving')
                  : scene
                    ? t('scenePage.updateScene')
                    : t('scenePage.createScene')}
              </button>
            </div>
            <div className="scene-controls">
              <label>
                {t('scenePage.mode')}
                <select
                  className="input"
                  value={mode}
                  onChange={(event) => setMode(event.target.value as SceneMode)}
                >
                  {modes.map((item) => (
                    <option key={item} value={item}>
                      {t(`scenePage.modes.${item}`)}
                    </option>
                  ))}
                </select>
              </label>
              {dataset?.kind === 'array' ? (
                <>
                  <label>
                    {t('scenePage.axis')}
                    <input
                      className="input"
                      type="number"
                      min="0"
                      max="3"
                      value={axis}
                      onChange={(event) => setAxis(Number(event.target.value))}
                    />
                  </label>
                  <label>
                    {t('scenePage.sliceIndex')}
                    <input
                      className="input"
                      type="number"
                      min="0"
                      value={index}
                      onChange={(event) => setIndex(Number(event.target.value))}
                    />
                  </label>
                </>
              ) : null}
              <label>
                {t('scenePage.colormap')}
                <select
                  className="input"
                  value={colormap}
                  onChange={(event) => setColormap(event.target.value)}
                >
                  {COLORMAPS.map((item) => (
                    <option key={item} value={item}>
                      {t(`scenePage.colormaps.${item}`)}
                    </option>
                  ))}
                </select>
              </label>
              {mode === 'isosurface' ? (
                <label>
                  {t('scenePage.isovalue')}
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
              <label>
                {t('scenePage.backend')}
                <select
                  className="input"
                  value={backend}
                  onChange={(event) => setBackend(event.target.value as Backend)}
                >
                  {BACKENDS.map((item) => (
                    <option
                      key={item}
                      value={item}
                      disabled={serverDisabled && (item === 'mayavi' || item === 'trame')}
                    >
                      {t(`scenePage.backends.${item}`)}
                    </option>
                  ))}
                </select>
              </label>
              {serverDisabled ? (
                <p className="muted scene-probe-hint">{t('scenePage.serverDisabled')}</p>
              ) : null}
            </div>
          </section>

          <TransferFunctionEditor value={transfer} onChange={setTransfer} histogram={bins} />

          <section className="card" aria-label={t('scenePage.canvas')}>
            <div className="panel-title">
              <h2>{t('scenePage.canvas')}</h2>
              {geometry?.sampled ? (
                <span className="route-notice">
                  {t('scenePage.lod', { lod: geometry.lod ?? 1 })}
                </span>
              ) : null}
            </div>
            {screenshot ? (
              <div className="inline-form">
                <a className="btn" href={screenshot} download="advp-scene.png">
                  {t('scenePage.downloadScreenshot')}
                </a>
                <button className="btn" type="button" onClick={() => setScreenshot(null)}>
                  {t('common.close')}
                </button>
              </div>
            ) : null}
            {geometry ? (
              <VtkScene
                geometry={geometry}
                colormap={colormap}
                isovalue={isovalue}
                clipping={clippingEnabled}
                transferFunction={transfer}
                onScreenshot={setScreenshot}
              />
            ) : (
              <p className="muted">{t('scenePage.canvasEmpty')}</p>
            )}
            {saved ? <p className="notice">{t('scenePage.saved')}</p> : null}
            {scene ? (
              <div className="inline-form scene-exports">
                <a className="btn" href={`/api/scenes/${scene.id}/export/python`}>
                  {t('scenePage.exportPython')}
                </a>
                <a className="btn" href={`/api/scenes/${scene.id}/export/json`}>
                  {t('scenePage.exportJson')}
                </a>
              </div>
            ) : null}
            {scene ? (
              <RenderPanel
                sceneId={scene.id}
                mode={mode}
                isovalue={isovalue}
                animation={{ frames, fps, startFrame }}
              />
            ) : null}
            {scene ? <SciViewPanel sceneId={scene.id} /> : null}
          </section>
        </div>

        <aside className="scene-side">
          <section className="card">
            <h2>{t('scenePage.clipping')}</h2>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={clippingEnabled}
                onChange={(event) => setClippingEnabled(event.target.checked)}
              />
              {t('scenePage.clippingEnabled')}
            </label>
            <p className="muted">{t('scenePage.clippingHint')}</p>
            <label>
              {t('scenePage.planeOrigin')}
              <input
                className="input"
                value={planeOrigin.join(', ')}
                onChange={(event) => setPlaneOrigin(parseVector(event.target.value))}
              />
            </label>
            <label>
              {t('scenePage.planeNormal')}
              <input
                className="input"
                value={planeNormal.join(', ')}
                onChange={(event) => setPlaneNormal(parseVector(event.target.value))}
              />
            </label>
          </section>

          <section className="card">
            <h2>{t('scenePage.lighting')}</h2>
            <label>
              {t('scenePage.ambient')}
              <input
                type="range"
                min="0"
                max="1"
                step="0.01"
                value={ambient}
                onChange={(event) => setAmbient(Number(event.target.value))}
              />
              <span className="muted">{ambient.toFixed(2)}</span>
            </label>
            <label>
              {t('scenePage.diffuse')}
              <input
                type="range"
                min="0"
                max="1"
                step="0.01"
                value={diffuse}
                onChange={(event) => setDiffuse(Number(event.target.value))}
              />
              <span className="muted">{diffuse.toFixed(2)}</span>
            </label>
          </section>

          <section className="card">
            <h2>{t('scenePage.animation')}</h2>
            <label>
              {t('scenePage.frames')}
              <input
                className="input"
                type="number"
                min="1"
                max="2000"
                value={frames}
                onChange={(event) => setFrames(Number(event.target.value))}
              />
            </label>
            <label>
              {t('scenePage.fps')}
              <input
                className="input"
                type="number"
                min="1"
                max="120"
                value={fps}
                onChange={(event) => setFps(Number(event.target.value))}
              />
            </label>
            <label>
              {t('scenePage.startFrame')}
              <input
                className="input"
                type="number"
                min="0"
                max="2000"
                value={startFrame}
                onChange={(event) => setStartFrame(Number(event.target.value))}
              />
            </label>
            <p className="muted">{t('scenePage.animationHint')}</p>
          </section>

          <section className="card">
            <h2>{t('scenePage.annotations')}</h2>
            <ul className="scene-annotations">
              {annotations.map((annotation, index) => (
                <li key={index}>
                  <input
                    className="input"
                    aria-label={t('scenePage.annotationText', { index: index + 1 })}
                    value={annotation.text}
                    onChange={(event) => {
                      const next = [...annotations]
                      next[index] = { ...annotation, text: event.target.value }
                      setAnnotations(next)
                    }}
                  />
                  <input
                    className="input"
                    aria-label={t('scenePage.annotationPosition', { index: index + 1 })}
                    value={annotation.position.join(', ')}
                    onChange={(event) => {
                      const next = [...annotations]
                      next[index] = {
                        ...annotation,
                        position: parseVector(event.target.value),
                      }
                      setAnnotations(next)
                    }}
                  />
                  <input
                    type="color"
                    aria-label={t('scenePage.annotationColor', { index: index + 1 })}
                    value={annotation.color}
                    onChange={(event) => {
                      const next = [...annotations]
                      next[index] = { ...annotation, color: event.target.value }
                      setAnnotations(next)
                    }}
                  />
                  <button
                    className="btn"
                    type="button"
                    aria-label={t('scenePage.removeAnnotation', { index: index + 1 })}
                    onClick={() => setAnnotations(annotations.filter((_, item) => item !== index))}
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
            <button
              className="btn"
              type="button"
              onClick={() =>
                setAnnotations([
                  ...annotations,
                  { text: '', position: [0, 0, 0], color: '#ffffff' },
                ])
              }
            >
              {t('scenePage.addAnnotation')}
            </button>
          </section>
        </aside>
      </div>
    </section>
  )
}

function parseVector(value: string): number[] {
  const parsed = value
    .split(',')
    .map((item) => Number(item.trim()))
    .filter((item) => Number.isFinite(item))
  return parsed.length === 3 ? parsed : [0, 0, 0]
}
