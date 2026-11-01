import type { SceneTransferFunction } from '../api/scenes'

export const DEFAULT_COLOR_POINTS: [number, string][] = [
  [0, '#440154'],
  [0.25, '#3b528b'],
  [0.5, '#21918c'],
  [0.75, '#5ec962'],
  [1, '#fde725'],
]

export const DEFAULT_OPACITY_POINTS: [number, number][] = [
  [0, 0],
  [0.5, 0.4],
  [1, 0.9],
]

function fromStops(
  stops: [number, string][],
  opacities: [number, number][] = DEFAULT_OPACITY_POINTS,
): SceneTransferFunction {
  return {
    colorPoints: stops.map(([x, color]) => ({ x, color })),
    opacityPoints: opacities.map(([x, opacity]) => ({ x, opacity })),
    interpolation: 'linear',
  }
}

export const TRANSFER_PRESETS: Record<string, SceneTransferFunction> = {
  viridis: fromStops(DEFAULT_COLOR_POINTS),
  grayscale: fromStops([
    [0, '#000000'],
    [0.25, '#404040'],
    [0.5, '#808080'],
    [0.75, '#c0c0c0'],
    [1, '#ffffff'],
  ]),
  hot: fromStops([
    [0, '#000000'],
    [0.33, '#ff0000'],
    [0.66, '#ffff00'],
    [1, '#ffffff'],
  ]),
  jet: fromStops([
    [0, '#000080'],
    [0.25, '#0080ff'],
    [0.5, '#00ffff'],
    [0.75, '#ffff00'],
    [1, '#ff0000'],
  ]),
}

export function defaultTransferFunction(): SceneTransferFunction {
  return cloneTransferFunction(TRANSFER_PRESETS.viridis)
}

export function cloneTransferFunction(value: SceneTransferFunction): SceneTransferFunction {
  return {
    colorPoints: value.colorPoints.map((point) => ({ ...point })),
    opacityPoints: value.opacityPoints.map((point) => ({ ...point })),
    interpolation: value.interpolation,
  }
}

export function normalizeTransferFunction(value: unknown): SceneTransferFunction {
  if (!value || typeof value !== 'object') return defaultTransferFunction()
  const candidate = value as Partial<SceneTransferFunction> & { points?: number[][] }
  if (Array.isArray(candidate.colorPoints) && Array.isArray(candidate.opacityPoints)) {
    return {
      colorPoints: candidate.colorPoints.map((point) => ({
        x: Number(point.x),
        color: String(point.color),
      })),
      opacityPoints: candidate.opacityPoints.map((point) => ({
        x: Number(point.x),
        opacity: Number(point.opacity),
      })),
      interpolation: candidate.interpolation === 'smooth' ? 'smooth' : 'linear',
    }
  }
  if (Array.isArray(candidate.points)) {
    return {
      ...defaultTransferFunction(),
      opacityPoints: candidate.points.map(([x, opacity]) => ({
        x: Number(x),
        opacity: Number(opacity),
      })),
    }
  }
  return defaultTransferFunction()
}

function hexChannel(value: string, offset: number): number {
  return Number.parseInt(value.slice(offset, offset + 2), 16)
}

function toHex(value: number): string {
  return Math.round(Math.max(0, Math.min(255, value)))
    .toString(16)
    .padStart(2, '0')
}

export function smoothColorPoints(
  points: SceneTransferFunction['colorPoints'],
  steps = 8,
): SceneTransferFunction['colorPoints'] {
  if (points.length < 2) return points
  const sorted = [...points].sort((a, b) => a.x - b.x)
  const result: SceneTransferFunction['colorPoints'] = []
  for (let index = 0; index < sorted.length - 1; index += 1) {
    const left = sorted[index]
    const right = sorted[index + 1]
    for (let step = 0; step < steps; step += 1) {
      const fraction = step / steps
      const eased = fraction * fraction * (3 - 2 * fraction)
      const channels = [1, 3, 5].map((offset) => {
        const start = hexChannel(left.color, offset)
        const end = hexChannel(right.color, offset)
        return start + (end - start) * eased
      })
      result.push({
        x: left.x + (right.x - left.x) * fraction,
        color: `#${channels.map(toHex).join('')}`,
      })
    }
  }
  result.push(sorted[sorted.length - 1])
  return result
}

export function smoothOpacityPoints(
  points: SceneTransferFunction['opacityPoints'],
  steps = 8,
): SceneTransferFunction['opacityPoints'] {
  if (points.length < 2) return points
  const sorted = [...points].sort((a, b) => a.x - b.x)
  const result: SceneTransferFunction['opacityPoints'] = []
  for (let index = 0; index < sorted.length - 1; index += 1) {
    const left = sorted[index]
    const right = sorted[index + 1]
    for (let step = 0; step < steps; step += 1) {
      const fraction = step / steps
      const eased = fraction * fraction * (3 - 2 * fraction)
      result.push({
        x: left.x + (right.x - left.x) * fraction,
        opacity: left.opacity + (right.opacity - left.opacity) * eased,
      })
    }
  }
  result.push(sorted[sorted.length - 1])
  return result
}

export function sortTransferFunction(value: SceneTransferFunction): SceneTransferFunction {
  return {
    colorPoints: [...value.colorPoints].sort((a, b) => a.x - b.x),
    opacityPoints: [...value.opacityPoints].sort((a, b) => a.x - b.x),
    interpolation: value.interpolation,
  }
}
