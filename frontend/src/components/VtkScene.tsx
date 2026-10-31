import { useEffect, useRef, useState } from 'react'

import { errorMessage } from '../api/projects'
import type { GeometryPayload, SceneTransferFunction } from '../api/scenes'

type VtkObject = { delete?: () => void }
type VtkRenderWindow = { render: () => void; getInteractor?: () => unknown }
type VtkRenderer = {
  addActor: (actor: unknown) => void
  addVolume?: (volume: unknown) => void
  resetCamera: () => void
  setBackground: (red: number, green: number, blue: number) => void
}
type VtkGenericRenderWindow = {
  setContainer: (node: HTMLElement) => void
  getRenderer: () => VtkRenderer
  getRenderWindow: () => VtkRenderWindow
  resize: () => void
  delete: () => void
}
type VtkModule = { newInstance: (initialValues?: Record<string, unknown>) => unknown }

type VtkRefs = {
  generic: VtkGenericRenderWindow
  renderWindow: VtkRenderWindow
  objects: VtkObject[]
  ctfModule: VtkModule
  ctf: VtkObject & { addRGBPoint: (x: number, r: number, g: number, b: number) => void }
}

const COLORMAPS: Record<string, [number, number, number][]> = {
  viridis: [
    [68, 1, 84],
    [59, 82, 139],
    [33, 145, 140],
    [94, 201, 98],
    [253, 231, 37],
  ],
  grayscale: [
    [0, 0, 0],
    [255, 255, 255],
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

export function VtkScene({
  geometry,
  colormap = 'viridis',
  isovalue = 0.5,
  clipping = false,
  transferFunction,
  onScreenshot,
}: {
  geometry: GeometryPayload
  colormap?: string
  isovalue?: number
  clipping?: boolean
  transferFunction?: SceneTransferFunction
  onScreenshot?: (dataUrl: string) => void
}) {
  const container = useRef<HTMLDivElement>(null)
  const refs = useRef<VtkRefs | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const node = container.current
    if (!node) return
    let cancelled = false
    let cleanup: (() => void) | null = null
    Promise.all([
      import('@kitware/vtk.js/Rendering/Profiles/Geometry'),
      import('@kitware/vtk.js/Rendering/Profiles/Volume'),
      import('@kitware/vtk.js/Rendering/Misc/GenericRenderWindow'),
      import('@kitware/vtk.js/Rendering/Core/Actor'),
      import('@kitware/vtk.js/Rendering/Core/Mapper'),
      import('@kitware/vtk.js/Common/DataModel/PolyData'),
      import('@kitware/vtk.js/Common/Core/Points'),
      import('@kitware/vtk.js/Common/Core/DataArray'),
      import('@kitware/vtk.js/Rendering/Core/ColorTransferFunction'),
      import('@kitware/vtk.js/Common/DataModel/PiecewiseFunction'),
      import('@kitware/vtk.js/Rendering/Core/ImageMapper'),
      import('@kitware/vtk.js/Rendering/Core/ImageSlice'),
      import('@kitware/vtk.js/Common/DataModel/ImageData'),
      import('@kitware/vtk.js/Filters/General/ImageMarchingCubes'),
      import('@kitware/vtk.js/Rendering/Core/VolumeMapper'),
      import('@kitware/vtk.js/Rendering/Core/Volume'),
    ])
      .then(
        ([
          _geometryProfile,
          _volumeProfile,
          genericModule,
          actorModule,
          mapperModule,
          polyDataModule,
          pointsModule,
          arrayModule,
          ctfModule,
          opacityModule,
          imageMapperModule,
          imageSliceModule,
          imageDataModule,
          marchingModule,
          volumeMapperModule,
          volumeModule,
        ]) => {
          void _geometryProfile
          void _volumeProfile
          if (cancelled) return
          const generic = (genericModule.default as unknown as VtkModule).newInstance({
            background: [0.04, 0.08, 0.15],
          }) as VtkGenericRenderWindow
          generic.setContainer(node)
          const renderer = generic.getRenderer()
          renderer.setBackground(0.04, 0.08, 0.15)
          const renderWindow = generic.getRenderWindow()
          const ctf = (ctfModule.default as unknown as VtkModule).newInstance() as VtkRefs['ctf']
          if (transferFunction) {
            applyTransferFunction(ctf, geometry, transferFunction)
          } else {
            applyColormap(ctf, geometry, colormap)
          }
          const objects: VtkObject[] = [ctf]

          if (geometry.mode === 'points' || geometry.mode === 'surface') {
            const points = geometry.points ?? []
            if (!points.length) throw new Error('点云为空')
            const positions = Float32Array.from(points.flatMap((point) => point.position))
            const vtkPoints = (pointsModule.default as unknown as VtkModule).newInstance({
              values: positions,
              numberOfComponents: 3,
            })
            const polyData = (polyDataModule.default as unknown as VtkModule).newInstance()
            ;(polyData as { setPoints: (value: unknown) => void }).setPoints(vtkPoints)
            const values = points.map((point) => point.value).filter((value) => value !== undefined)
            if (values.length === points.length) {
              const scalars = (arrayModule.default as unknown as VtkModule).newInstance({
                values: Float32Array.from(values as number[]),
                numberOfComponents: 1,
              })
              ;(
                polyData as { getPointData: () => { setScalars: (value: unknown) => void } }
              ).getPointData().setScalars(scalars)
              objects.push(scalars as VtkObject)
            }
            const mapper = (mapperModule.default as unknown as VtkModule).newInstance() as {
              setInputData: (value: unknown) => void
              setLookupTable: (value: unknown) => void
              setScalarRange: (min: number, max: number) => void
              setScalarVisibility: (value: boolean) => void
            }
            mapper.setInputData(polyData)
            mapper.setLookupTable(ctf)
            const [minValue, maxValue] = geometry.range ?? [0, 1]
            mapper.setScalarRange(minValue ?? 0, maxValue ?? 1)
            mapper.setScalarVisibility(values.length === points.length)
            const actor = (actorModule.default as unknown as VtkModule).newInstance() as {
              setMapper: (value: unknown) => void
              getProperty: () => {
                setRepresentationToPoints: () => void
                setPointSize: (value: number) => void
              }
            }
            actor.setMapper(mapper)
            actor.getProperty().setRepresentationToPoints()
            actor.getProperty().setPointSize(4)
            renderer.addActor(actor)
            objects.push(vtkPoints as VtkObject, polyData as VtkObject, mapper as VtkObject, actor as VtkObject)
          } else if (geometry.mode === 'slice' || geometry.mode === 'volume' || geometry.mode === 'isosurface') {
            const values = flattenValues(geometry)
            const shape = geometry.mode === 'slice'
              ? [geometry.cols ?? 0, geometry.rows ?? 0, 1]
              : geometry.display_shape ?? geometry.shape ?? []
            if (!values.length || shape.length < 2) {
              throw new Error('该体积数据需要服务端 Mayavi 渲染')
            }
            const imageData = (imageDataModule.default as unknown as VtkModule).newInstance() as {
              setDimensions: (x: number, y: number, z: number) => void
              setSpacing: (x: number, y: number, z: number) => void
              setOrigin: (x: number, y: number, z: number) => void
              getPointData: () => { setScalars: (value: unknown) => void }
            }
            imageData.setDimensions(shape[0], shape[1], shape[2] ?? 1)
            const spacing = geometry.spacing ?? [1, 1, 1]
            imageData.setSpacing(spacing[0] ?? 1, spacing[1] ?? 1, spacing[2] ?? 1)
            imageData.setOrigin(0, 0, 0)
            const scalars = (arrayModule.default as unknown as VtkModule).newInstance({
              values: Float32Array.from(values),
              numberOfComponents: 1,
            })
            imageData.getPointData().setScalars(scalars)
            objects.push(imageData as VtkObject, scalars as VtkObject)
            if (geometry.mode === 'slice') {
              const mapper = (imageMapperModule.default as unknown as VtkModule).newInstance() as {
                setInputData: (value: unknown) => void
                setSlicingMode: (value: number) => void
                setLookupTable: (value: unknown) => void
                setScalarRange: (min: number, max: number) => void
              }
              mapper.setInputData(imageData)
              mapper.setSlicingMode(2)
              mapper.setLookupTable(ctf)
              const [minValue, maxValue] = geometry.range ?? [0, 1]
              mapper.setScalarRange(minValue ?? 0, maxValue ?? 1)
              const actor = (imageSliceModule.default as unknown as VtkModule).newInstance() as {
                setMapper: (value: unknown) => void
              }
              actor.setMapper(mapper)
              renderer.addActor(actor)
              objects.push(mapper as VtkObject, actor as VtkObject)
            } else if (geometry.mode === 'isosurface') {
              const marching = (marchingModule.default as unknown as VtkModule).newInstance() as {
                setInputData: (value: unknown) => void
                setContourValue: (value: number) => void
                getOutputPort: () => unknown
              }
              marching.setInputData(imageData)
              marching.setContourValue(isovalue)
              const mapper = (mapperModule.default as unknown as VtkModule).newInstance() as {
                setInputConnection: (value: unknown) => void
                setLookupTable: (value: unknown) => void
              }
              mapper.setInputConnection(marching.getOutputPort())
              mapper.setLookupTable(ctf)
              const actor = (actorModule.default as unknown as VtkModule).newInstance() as {
                setMapper: (value: unknown) => void
              }
              actor.setMapper(mapper)
              renderer.addActor(actor)
              objects.push(marching as VtkObject, mapper as VtkObject, actor as VtkObject)
            } else {
              const mapper = (volumeMapperModule.default as unknown as VtkModule).newInstance() as {
                setInputData: (value: unknown) => void
              }
              mapper.setInputData(imageData)
              const volume = (volumeModule.default as unknown as VtkModule).newInstance() as {
                setMapper: (value: unknown) => void
                getProperty: () => {
                  setRGBTransferFunction: (index: number, ctf: unknown) => void
                  setScalarOpacity: (index: number, opacity: unknown) => void
                }
              }
              volume.setMapper(mapper)
              volume.getProperty().setRGBTransferFunction(0, ctf)
              if (transferFunction) {
                const opacity = (
                  opacityModule.default as unknown as VtkModule
                ).newInstance() as VtkObject & { addPoint: (x: number, value: number) => void }
                applyOpacityFunction(opacity, geometry, transferFunction)
                volume.getProperty().setScalarOpacity(0, opacity)
                objects.push(opacity)
              }
              renderer.addVolume?.(volume)
              objects.push(mapper as VtkObject, volume as VtkObject)
            }
          }
          if (clipping && geometry.mode !== 'slice') {
            // Clipping planes are applied by the server renderer for reliable parity.
          }
          renderer.resetCamera()
          renderWindow.render()
          refs.current = { generic, renderWindow, objects, ctfModule: ctfModule.default as unknown as VtkModule, ctf }
          setReady(true)
          cleanup = () => {
            refs.current = null
            for (const object of objects) object.delete?.()
            generic.delete()
          }
        },
      )
      .catch((err: unknown) => {
        if (!cancelled) setError(errorMessage(err))
      })
    return () => {
      cancelled = true
      cleanup?.()
    }
  }, [geometry, colormap, isovalue, clipping, transferFunction])

  useEffect(() => {
    if (ready && refs.current) {
      refs.current.renderWindow.render()
    }
  }, [ready])

  function screenshot() {
    const canvas = container.current?.querySelector('canvas')
    if (!canvas) return
    onScreenshot?.(canvas.toDataURL('image/png'))
  }

  return (
    <div className="vtk-scene-block">
      {error ? <p className="error">{error}</p> : null}
      <div className="inline-form">
        <button className="button" onClick={screenshot} disabled={!ready}>
          保存截图
        </button>
        <span className="muted">
          {geometry.mode} · {geometry.sampled ? `LOD ${geometry.lod ?? 1}` : '原始'}
          {geometry.display_shape ? ` · ${geometry.display_shape.join(' × ')}` : ''}
        </span>
      </div>
      <div className="vtk-scene" ref={container} data-testid="vtk-scene" />
    </div>
  )
}

function applyColormap(ctf: VtkRefs['ctf'], geometry: GeometryPayload, name: string) {
  const stops = COLORMAPS[name] ?? COLORMAPS.viridis
  const [minValue, maxValue] = geometry.range ?? [0, 1]
  const min = minValue ?? 0
  const max = maxValue ?? 1
  const span = max > min ? max - min : 1
  const last = Math.max(1, stops.length - 1)
  stops.forEach((rgb, index) => {
    ctf.addRGBPoint(min + (span * index) / last, rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)
  })
}

function scalarRange(geometry: GeometryPayload): [number, number] {
  const [minValue, maxValue] = geometry.range ?? [0, 1]
  const min = minValue ?? 0
  const max = maxValue ?? 1
  return max > min ? [min, max] : [min, min + 1]
}

function applyTransferFunction(
  ctf: VtkRefs['ctf'],
  geometry: GeometryPayload,
  transferFunction: SceneTransferFunction,
) {
  const [min, max] = scalarRange(geometry)
  for (const point of transferFunction.colorPoints) {
    const [red, green, blue] = hexToRgb(point.color)
    ctf.addRGBPoint(min + (max - min) * point.x, red, green, blue)
  }
}

function applyOpacityFunction(
  opacity: { addPoint: (x: number, value: number) => void },
  geometry: GeometryPayload,
  transferFunction: SceneTransferFunction,
) {
  const [min, max] = scalarRange(geometry)
  for (const point of transferFunction.opacityPoints) {
    opacity.addPoint(min + (max - min) * point.x, point.opacity)
  }
}

function hexToRgb(value: string): [number, number, number] {
  if (!/^#[0-9A-Fa-f]{6}$/.test(value)) return [1, 1, 1]
  return [
    Number.parseInt(value.slice(1, 3), 16) / 255,
    Number.parseInt(value.slice(3, 5), 16) / 255,
    Number.parseInt(value.slice(5, 7), 16) / 255,
  ]
}

function flattenValues(geometry: GeometryPayload): number[] {
  const raw = geometry.values
  if (!raw) return []
  if (Array.isArray(raw) && raw.length > 0 && Array.isArray(raw[0])) {
    return (raw as (number | null)[][]).flat().map((value) => value ?? 0)
  }
  return (raw as (number | null)[]).map((value) => value ?? 0)
}
