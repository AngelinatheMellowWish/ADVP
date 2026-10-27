import DeckGL from '@deck.gl/react'
import { HexagonLayer } from '@deck.gl/aggregation-layers'
import { GeoJsonLayer, PathLayer, ScatterplotLayer } from '@deck.gl/layers'
import i18nCountries from 'i18n-iso-countries'
import enLocale from 'i18n-iso-countries/langs/en.json'
import zhLocale from 'i18n-iso-countries/langs/zh.json'
import { useMemo, useState } from 'react'
import { feature } from 'topojson-client'
import countries from 'world-atlas/countries-110m.json'
import admin1Data from '../data/ne_10m_admin_1_states_provinces.json'

i18nCountries.registerLocale(enLocale)
i18nCountries.registerLocale(zhLocale)

type Position = [number, number]
type ViewState = {
  longitude: number
  latitude: number
  zoom: number
  pitch: number
  bearing: number
}

type MapLayer =
  | { type: 'scatter'; data: { position: Position; value?: number; size?: number; label?: string }[] }
  | { type: 'path'; data: { path: Position[]; label?: string }[] }
  | { type: 'hexagon'; data: { position: Position; weight?: number }[] }
  | { type: 'region'; data: { region: string; value: number }[] }

export type DeckPayload = {
  layers?: MapLayer[]
  viewState?: Partial<ViewState>
  regionMode?: string
  title?: string
  meta?: Record<string, unknown>
}

type CountryProperties = { name?: string; name_zh?: string; name_en?: string }
type Admin1Properties = CountryProperties & {
  admin?: string
  iso_3166_2?: string
  adm0_a3?: string
}
type CountryFeature = {
  type: 'Feature'
  id?: string | number
  properties?: CountryProperties
  geometry: unknown
}
type Admin1Feature = {
  type: 'Feature'
  properties?: Admin1Properties
  geometry: unknown
}
type CountryCollection = { type: 'FeatureCollection'; features: CountryFeature[] }
type Admin1Collection = { type: 'FeatureCollection'; features: Admin1Feature[] }

const WORLD = feature(
  countries as never,
  (countries as { objects: { countries: unknown } }).objects.countries as never,
) as unknown as CountryCollection
const ADMIN1 = admin1Data as unknown as Admin1Collection

const COUNTRY_KEYS = buildCountryKeys(WORLD.features)
const ADMIN1_KEYS = buildAdmin1Keys(ADMIN1.features)

const VIRIDIS: [number, number, number][] = [
  [68, 1, 84],
  [59, 82, 139],
  [33, 145, 140],
  [94, 201, 98],
  [253, 231, 37],
]

export function DeckFigure({
  payload,
  selectionId,
}: {
  payload: DeckPayload
  selectionId: string
}) {
  const initial = payload.viewState ?? {}
  const [viewState, setViewState] = useState<ViewState>({
    longitude: initial.longitude ?? 0,
    latitude: initial.latitude ?? 20,
    zoom: initial.zoom ?? 1.2,
    pitch: initial.pitch ?? 0,
    bearing: initial.bearing ?? 0,
  })

  const { layers, unmatched, valueRange, regionMode } = useMemo(
    () => buildLayers(payload.layers ?? []),
    [payload.layers],
  )

  const reset = () => {
    setViewState({
      longitude: initial.longitude ?? 0,
      latitude: initial.latitude ?? 20,
      zoom: initial.zoom ?? 1.2,
      pitch: initial.pitch ?? 0,
      bearing: initial.bearing ?? 0,
    })
  }

  const download = () => {
    const canvas = document.querySelector<HTMLCanvasElement>('[data-testid="deck-figure"] canvas')
    if (!canvas) return
    const link = document.createElement('a')
    link.href = canvas.toDataURL('image/png')
    link.download = `advp-${selectionId}.png`
    link.click()
  }

  return (
    <>
      <div className="chart-controls">
        <button className="button" onClick={reset}>
          复位视图
        </button>
        <button className="button" onClick={download}>
          下载 PNG
        </button>
        <span className="muted">
          离线底图 · {layers.length} 层
          {regionMode ? ` · 区域层级: ${regionMode === 'admin1' ? 'admin-1' : '国家'}` : ''}
          {valueRange ? ` · 值域 ${valueRange[0].toFixed(3)}–${valueRange[1].toFixed(3)}` : ''}
          {unmatched > 0 ? ` · 未匹配区域 ${unmatched}` : ''}
        </span>
      </div>
      <div className="chart-figure chart-deck" data-testid="deck-figure">
        <DeckGL
          initialViewState={viewState}
          viewState={viewState}
          controller
          layers={layers as never}
          onViewStateChange={({ viewState: next }) => setViewState(next as ViewState)}
          getTooltip={({ object }) =>
            object && typeof object === 'object'
              ? JSON.stringify(object).slice(0, 240)
              : null
          }
        />
      </div>
    </>
  )
}

function buildLayers(rawLayers: MapLayer[]) {
  const deckLayers: unknown[] = [
    new GeoJsonLayer({
      id: 'world-countries',
      data: WORLD.features as never,
      filled: true,
      stroked: true,
      getFillColor: [22, 35, 61],
      getLineColor: [49, 71, 107],
      lineWidthMinPixels: 0.5,
      pickable: false,
    }),
  ]
  let unmatched = 0
  let valueRange: [number, number] | null = null
  let regionMode: 'admin1' | 'country' | null = null

  for (const layer of rawLayers) {
    if (layer.type === 'scatter') {
      const values = layer.data
        .map((item) => item.value)
        .filter((value): value is number => typeof value === 'number')
      valueRange = values.length ? [Math.min(...values), Math.max(...values)] : null
      deckLayers.push(
        new ScatterplotLayer({
          id: 'geo-scatter',
          data: layer.data,
          getPosition: (item: { position: Position }) => item.position,
          getRadius: (item: { size?: number }) => 4 + Math.abs(item.size ?? 8) * 0.8,
          radiusMinPixels: 3,
          radiusMaxPixels: 26,
          getFillColor: (item: { value?: number }) =>
            colorFor(item.value, valueRange?.[0], valueRange?.[1]),
          pickable: true,
        }),
      )
    } else if (layer.type === 'path') {
      deckLayers.push(
        new PathLayer({
          id: 'geo-path',
          data: layer.data,
          getPath: (item: { path: Position[] }) => item.path,
          getColor: [96, 165, 250],
          widthUnits: 'pixels',
          getWidth: 2,
          widthMinPixels: 1,
          pickable: true,
        }),
      )
    } else if (layer.type === 'hexagon') {
      deckLayers.push(
        new HexagonLayer({
          id: 'geo-hexagon',
          data: layer.data,
          getPosition: (item: { position: Position }) => item.position,
          getColorWeight: (item: { weight?: number }) => item.weight ?? 1,
          radius: 20_000,
          elevationScale: 2,
          extruded: false,
          pickable: true,
        }),
      )
    } else if (layer.type === 'region') {
      const values = layer.data.map((item) => item.value)
      valueRange = values.length ? [Math.min(...values), Math.max(...values)] : null
      const match = matchRegions(layer.data)
      regionMode = match.mode
      unmatched = match.unmatched
      deckLayers.push(
        new GeoJsonLayer({
          id: 'geo-region',
          data: match.features as never,
          filled: true,
          stroked: true,
          getFillColor: (item: CountryFeature | Admin1Feature) => {
            const value = match.valueByFeature.get(item)
            return colorFor(value, valueRange?.[0], valueRange?.[1])
          },
          getLineColor: [49, 71, 107],
          lineWidthMinPixels: 0.5,
          pickable: true,
        }),
      )
    }
  }
  return { layers: deckLayers, unmatched, valueRange, regionMode }
}

function buildCountryKeys(features: CountryFeature[]): Map<string, CountryFeature> {
  const keys = new Map<string, CountryFeature>()
  for (const feature of features) {
    const id = String(feature.id ?? '')
    const alpha2 = id ? i18nCountries.numericToAlpha2(id) : undefined
    const alpha3 = alpha2 ? i18nCountries.alpha2ToAlpha3(alpha2) : undefined
    const names = [
      feature.properties?.name,
      feature.properties?.name_en,
      feature.properties?.name_zh,
      alpha2,
      alpha3,
      id,
      alpha2 ? i18nCountries.getName(alpha2, 'en') : undefined,
      alpha2 ? i18nCountries.getName(alpha2, 'zh') : undefined,
    ]
    for (const name of names) {
      const key = normalizeRegion(name ?? '')
      if (key) keys.set(key, feature)
    }
  }
  return keys
}

function buildAdmin1Keys(features: Admin1Feature[]): Map<string, Admin1Feature> {
  const keys = new Map<string, Admin1Feature>()
  for (const feature of features) {
    const properties = feature.properties ?? {}
    const names = [
      properties.name,
      properties.name_en,
      properties.name_zh,
      properties.iso_3166_2,
      properties.admin && properties.name ? `${properties.admin}:${properties.name}` : undefined,
      properties.adm0_a3 && properties.name
        ? `${properties.adm0_a3}:${properties.name}`
        : undefined,
    ]
    for (const name of names) {
      const key = normalizeRegion(name ?? '')
      if (key) keys.set(key, feature)
    }
  }
  return keys
}

function matchLayer<T extends CountryFeature | Admin1Feature>(
  keys: Map<string, T>,
  data: { region: string; value: number }[],
) {
  const valueByFeature = new Map<T, number>()
  let unmatched = 0
  for (const item of data) {
    const feature = keys.get(normalizeRegion(item.region))
    if (!feature) {
      unmatched += 1
      continue
    }
    valueByFeature.set(feature, (valueByFeature.get(feature) ?? 0) + item.value)
  }
  return {
    mode: null as 'admin1' | 'country' | null,
    features: [...valueByFeature.keys()],
    valueByFeature,
    unmatched,
  }
}

function matchRegions(data: { region: string; value: number }[]) {
  const admin = matchLayer(ADMIN1_KEYS, data)
  const country = matchLayer(COUNTRY_KEYS, data)
  if (admin.features.length > 0 && admin.features.length >= country.features.length) {
    return { ...admin, mode: 'admin1' as const }
  }
  return { ...country, mode: 'country' as const }
}

function colorFor(value: number | undefined, min?: number, max?: number): [number, number, number, number] {
  if (value === undefined || min === undefined || max === undefined || max <= min) {
    return [59, 130, 246, 200]
  }
  const ratio = Math.max(0, Math.min(1, (value - min) / (max - min)))
  const scaled = ratio * (VIRIDIS.length - 1)
  const index = Math.min(VIRIDIS.length - 2, Math.floor(scaled))
  const fraction = scaled - index
  const start = VIRIDIS[index]
  const end = VIRIDIS[index + 1]
  return [
    Math.round(start[0] + (end[0] - start[0]) * fraction),
    Math.round(start[1] + (end[1] - start[1]) * fraction),
    Math.round(start[2] + (end[2] - start[2]) * fraction),
    210,
  ]
}

function normalizeRegion(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()
}
