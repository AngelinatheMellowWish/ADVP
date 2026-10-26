import { useEffect, useRef, useState } from 'react'

import {
  getImagingMeta,
  getImagingSlice,
  type ImagingMeta,
  type ImagingSlice,
} from '../api/imaging'
import { errorMessage } from '../api/projects'

type VtkGenericRenderWindow = {
  setContainer: (node: HTMLElement) => void
  getRenderer: () => VtkRenderer
  getRenderWindow: () => VtkRenderWindow
  resize: () => void
  delete: () => void
}
type VtkRenderer = {
  addActor: (actor: unknown) => void
  resetCamera: () => void
  setBackground: (red: number, green: number, blue: number) => void
}
type VtkRenderWindow = {
  render: () => void
  getInteractor: () => { setInteractorStyle: (style: unknown) => void }
}
type VtkImageMapper = {
  setInputData: (data: unknown) => void
  setSlicingMode: (mode: number) => void
  delete: () => void
}
type VtkImageProperty = {
  setRGBTransferFunction: (index: number, ctf: unknown) => void
  setUseLookupTableScalarRange: (value: boolean) => void
  setColorWindow: (value: number) => void
  setColorLevel: (value: number) => void
  setInterpolationTypeToLinear: () => void
}
type VtkImageSlice = {
  setMapper: (mapper: unknown) => void
  getProperty: () => VtkImageProperty
  delete: () => void
}
type VtkImageData = {
  setDimensions: (x: number, y: number, z: number) => void
  setSpacing: (x: number, y: number, z: number) => void
  setOrigin: (x: number, y: number, z: number) => void
  getPointData: () => { setScalars: (scalars: unknown) => void }
  delete: () => void
}
type VtkDataArray = { delete: () => void }
type VtkCTF = {
  addRGBPoint: (x: number, red: number, green: number, blue: number) => void
  delete: () => void
}
type VtkModule = {
  newInstance: (initialValues?: Record<string, unknown>) => unknown
}

type VtkRefs = {
  renderWindow: VtkRenderWindow
  mapper: VtkImageMapper
  actor: VtkImageSlice
  imageData: VtkImageData
  scalars: VtkDataArray
  ctf: VtkCTF
  ctfModule: VtkModule
  generic: VtkGenericRenderWindow
}

type Annotation = { text: string; x?: number; y?: number; showarrow?: boolean }

const COLORMAPS: Record<string, [number, number, number][]> = {
  grayscale: [
    [0, 0, 0],
    [255, 255, 255],
  ],
  viridis: [
    [68, 1, 84],
    [59, 82, 139],
    [33, 145, 140],
    [94, 201, 98],
    [253, 231, 37],
  ],
  hot: [
    [0, 0, 0],
    [255, 0, 0],
    [255, 255, 0],
    [255, 255, 255],
  ],
  jet: [
    [0, 0, 128],
    [0, 128, 255],
    [0, 255, 255],
    [255, 255, 0],
    [255, 0, 0],
  ],
}

export type ImagingPayload = {
  dataset_id?: string
  annotations?: Annotation[]
}

export function VtkImageFigure({
  datasetId,
  imaging,
}: {
  datasetId: string
  imaging?: ImagingPayload
}) {
  const [meta, setMeta] = useState<ImagingMeta | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [indices, setIndices] = useState<Record<number, number>>({})
  const [volume, setVolume] = useState(0)
  const [windowMin, setWindowMin] = useState(0)
  const [windowMax, setWindowMax] = useState(1)
  const [colormap, setColormap] = useState('grayscale')
  const [invert, setInvert] = useState(false)

  useEffect(() => {
    let cancelled = false
    getImagingMeta(datasetId)
      .then((result) => {
        if (cancelled) return
        setMeta(result)
        const initial: Record<number, number> = {}
        for (const axis of result.slice_axes) initial[axis.axis] = 0
        setIndices(initial)
        const low = result.window.min ?? 0
        const high = result.window.max ?? (low + 1)
        setWindowMin(low)
        setWindowMax(high <= low ? low + 1 : high)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(errorMessage(err))
      })
    return () => {
      cancelled = true
    }
  }, [datasetId])

  const views = meta?.slice_axes.length ? meta.slice_axes : meta ? [{ axis: 0, name: 'image', size: 1 }] : []

  function reset() {
    const initial: Record<number, number> = {}
    for (const axis of meta?.slice_axes ?? []) initial[axis.axis] = 0
    setIndices(initial)
    setVolume(0)
    if (meta) {
      const low = meta.window.min ?? 0
      const high = meta.window.max ?? (low + 1)
      setWindowMin(low)
      setWindowMax(high <= low ? low + 1 : high)
    }
  }

  function download() {
    const canvas = document.querySelector<HTMLCanvasElement>('[data-testid="vtk-slice"] canvas')
    if (!canvas) return
    const link = document.createElement('a')
    link.href = canvas.toDataURL('image/png')
    link.download = `advp-imaging-${datasetId}.png`
    link.click()
  }

  if (error) return <p className="error">{error}</p>
  if (!meta) return <p className="muted">正在读取影像元数据…</p>

  return (
    <>
      <div className="chart-controls">
        {meta.volume_count > 1 ? (
          <label>
            时间/体索引
            <input
              type="range"
              min={0}
              max={meta.volume_count - 1}
              value={volume}
              onChange={(event) => setVolume(Number(event.target.value))}
            />
            <span className="muted">
              {volume + 1}/{meta.volume_count}
            </span>
          </label>
        ) : null}
        {views.map((axis) => (
          <label key={axis.axis}>
            {axis.name} 切片
            <input
              type="range"
              min={0}
              max={Math.max(0, axis.size - 1)}
              value={indices[axis.axis] ?? 0}
              onChange={(event) =>
                setIndices((current) => ({ ...current, [axis.axis]: Number(event.target.value) }))
              }
            />
            <span className="muted">
              {(indices[axis.axis] ?? 0) + 1}/{axis.size}
            </span>
          </label>
        ))}
        <label>
          伪彩
          <select value={colormap} onChange={(event) => setColormap(event.target.value)}>
            <option value="grayscale">灰度</option>
            <option value="viridis">Viridis</option>
            <option value="hot">Hot</option>
            <option value="jet">Jet</option>
          </select>
        </label>
        <label>
          窗宽下限
          <input
            type="number"
            value={windowMin}
            onChange={(event) => setWindowMin(Number(event.target.value))}
          />
        </label>
        <label>
          窗宽上限
          <input
            type="number"
            value={windowMax}
            onChange={(event) => setWindowMax(Number(event.target.value))}
          />
        </label>
        <label className="inline-check">
          <input
            type="checkbox"
            checked={invert}
            onChange={(event) => setInvert(event.target.checked)}
          />
          反色
        </label>
        <button className="button" onClick={reset}>
          复位
        </button>
        <button className="button" onClick={download}>
          下载 PNG
        </button>
      </div>
      <p className="muted">
        {meta.format} · {meta.shape.join(' × ')} · {meta.dtype ?? 'unknown'}
        {meta.units ? ` · ${meta.units}` : ''} · 窗宽 [{windowMin}, {windowMax}]
      </p>
      <div className="vtk-grid">
        {views.map((axis, index) => (
          <VtkSliceView
            key={`${axis.axis}-${indices[axis.axis] ?? 0}-${volume}`}
            datasetId={datasetId}
            axis={axis.axis}
            index={indices[axis.axis] ?? 0}
            volume={volume}
            windowMin={windowMin}
            windowMax={windowMax}
            colormap={colormap}
            invert={invert}
            crosshair={crosshairFor(axis.axis, indices, meta)}
            annotations={index === 0 ? imaging?.annotations ?? [] : []}
          />
        ))}
      </div>
    </>
  )
}

function VtkSliceView({
  datasetId,
  axis,
  index,
  volume,
  windowMin,
  windowMax,
  colormap,
  invert,
  crosshair,
  annotations,
}: {
  datasetId: string
  axis: number
  index: number
  volume: number
  windowMin: number
  windowMax: number
  colormap: string
  invert: boolean
  crosshair: { x: number; y: number } | null
  annotations: Annotation[]
}) {
  const container = useRef<HTMLDivElement>(null)
  const refs = useRef<VtkRefs | null>(null)
  const [slice, setSlice] = useState<ImagingSlice | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    let cancelled = false
    setError(null)
    getImagingSlice(datasetId, axis, index, volume)
      .then((result) => {
        if (!cancelled) setSlice(result)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(errorMessage(err))
      })
    return () => {
      cancelled = true
    }
  }, [datasetId, axis, index, volume])

  useEffect(() => {
    const node = container.current
    if (!node || !slice) return
    let cancelled = false
    let cleanup: (() => void) | null = null
    Promise.all([
      import('@kitware/vtk.js/Rendering/Misc/GenericRenderWindow'),
      import('@kitware/vtk.js/Rendering/Core/ImageMapper'),
      import('@kitware/vtk.js/Rendering/Core/ImageSlice'),
      import('@kitware/vtk.js/Common/DataModel/ImageData'),
      import('@kitware/vtk.js/Common/Core/DataArray'),
      import('@kitware/vtk.js/Rendering/Core/ColorTransferFunction'),
      import('@kitware/vtk.js/Interaction/Style/InteractorStyleImage'),
    ])
      .then(
        ([
          genericModule,
          mapperModule,
          sliceModule,
          imageModule,
          arrayModule,
          ctfModule,
          styleModule,
        ]) => {
          if (cancelled) return
          const generic = (genericModule.default as unknown as VtkModule).newInstance({
            background: [0.04, 0.08, 0.15],
          }) as VtkGenericRenderWindow
          generic.setContainer(node)
          const renderer = generic.getRenderer()
          renderer.setBackground(0.04, 0.08, 0.15)
          const renderWindow = generic.getRenderWindow()
          renderWindow.getInteractor().setInteractorStyle(
            (styleModule.default as unknown as VtkModule).newInstance(),
          )
          const mapper = (mapperModule.default as unknown as VtkModule).newInstance() as VtkImageMapper
          const actor = (sliceModule.default as unknown as VtkModule).newInstance() as VtkImageSlice
          const imageData = (imageModule.default as unknown as VtkModule).newInstance() as VtkImageData
          const values = Float32Array.from(slice.values.flat().map((value) => value ?? 0))
          const scalars = (arrayModule.default as unknown as VtkModule).newInstance({
            values,
            numberOfComponents: 1,
          }) as VtkDataArray
          imageData.setDimensions(slice.cols, slice.rows, 1)
          imageData.setSpacing(1, 1, 1)
          imageData.setOrigin(0, 0, 0)
          imageData.getPointData().setScalars(scalars)
          mapper.setInputData(imageData)
          mapper.setSlicingMode(2)
          actor.setMapper(mapper)
          const ctf = (ctfModule.default as unknown as VtkModule).newInstance() as VtkCTF
          const property = actor.getProperty()
          property.setUseLookupTableScalarRange(true)
          property.setInterpolationTypeToLinear()
          property.setRGBTransferFunction(0, ctf)
          renderer.addActor(actor)
          renderer.resetCamera()
          renderWindow.render()
          refs.current = {
            renderWindow,
            mapper,
            actor,
            imageData,
            scalars,
            ctf,
            ctfModule: ctfModule.default as unknown as VtkModule,
            generic,
          }
          setReady(true)
          cleanup = () => {
            refs.current = null
            mapper.delete()
            actor.delete()
            imageData.delete()
            scalars.delete()
            ctf.delete()
            generic.delete()
          }
        },
      )
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'VTK 渲染失败')
      })
    return () => {
      cancelled = true
      cleanup?.()
    }
  }, [slice])

  useEffect(() => {
    const current = refs.current
    if (!current) return
    const previous = current.ctf
    const ctf = current.ctfModule.newInstance() as VtkCTF
    applyColormap(ctf, windowMin, windowMax, colormap, invert)
    const property = current.actor.getProperty()
    property.setRGBTransferFunction(0, ctf)
    property.setColorWindow(Math.max(1e-6, windowMax - windowMin))
    property.setColorLevel((windowMax + windowMin) / 2)
    current.ctf = ctf
    previous.delete()
    current.renderWindow.render()
  }, [ready, windowMin, windowMax, colormap, invert])

  return (
    <div className="vtk-slice-block">
      <p className="muted">
        轴 {slice?.axis_name ?? axis} · 切片 {index + 1}
        {slice ? ` · ${slice.rows}×${slice.cols}` : ''}
      </p>
      {error ? <p className="error">{error}</p> : null}
      <div className="vtk-slice" ref={container} data-testid="vtk-slice">
        {crosshair ? (
          <div className="vtk-crosshair" aria-hidden="true">
            <span className="vtk-crosshair-v" style={{ left: `${crosshair.x * 100}%` }} />
            <span className="vtk-crosshair-h" style={{ top: `${crosshair.y * 100}%` }} />
          </div>
        ) : null}
        {slice
          ? annotations.map((annotation, position) => (
              <span
                className="vtk-annotation"
                key={`${annotation.text}-${position}`}
                style={{
                  left: `${((annotation.x ?? slice.cols / 2) / slice.cols) * 100}%`,
                  top: `${((annotation.y ?? slice.rows / 2) / slice.rows) * 100}%`,
                }}
              >
                {annotation.text}
              </span>
            ))
          : null}
      </div>
    </div>
  )
}

function applyColormap(
  ctf: VtkCTF,
  min: number,
  max: number,
  name: string,
  invert: boolean,
) {
  const stops = [...(COLORMAPS[name] ?? COLORMAPS.grayscale)]
  if (invert) stops.reverse()
  const span = max - min
  const last = Math.max(1, stops.length - 1)
  stops.forEach((rgb, index) => {
    ctf.addRGBPoint(min + (span * index) / last, rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)
  })
}

function crosshairFor(
  axis: number,
  indices: Record<number, number>,
  meta: ImagingMeta,
): { x: number; y: number } | null {
  const spatial = meta.slice_axes.filter((item) => item.axis !== axis)
  if (spatial.length < 2) return null
  const rowsAxis = spatial[0]
  const colsAxis = spatial[1]
  const rows = meta.shape[rowsAxis.axis] || 1
  const cols = meta.shape[colsAxis.axis] || 1
  return {
    x: (indices[colsAxis.axis] ?? 0) / cols,
    y: (indices[rowsAxis.axis] ?? 0) / rows,
  }
}
