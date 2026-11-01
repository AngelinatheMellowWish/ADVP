import { useId, useState, type PointerEvent as ReactPointerEvent } from 'react'
import { useTranslation } from 'react-i18next'

import type { SceneTransferFunction } from '../api/scenes'
import {
  cloneTransferFunction,
  smoothColorPoints,
  smoothOpacityPoints,
} from '../state/transferFunction'

type DragTarget = { kind: 'color' | 'opacity'; index: number } | null

function clamp(value: number, min = 0, max = 1): number {
  return Math.max(min, Math.min(max, value))
}

function opacityY(opacity: number): number {
  return 92 - clamp(opacity) * 80
}

export function TransferCurve({
  value,
  histogram = [],
  onChange,
}: {
  value: SceneTransferFunction
  histogram?: number[]
  onChange?: (next: SceneTransferFunction) => void
}) {
  const { t } = useTranslation()
  const gradientId = useId()
  const [drag, setDrag] = useState<DragTarget>(null)
  const maxBar = Math.max(1, ...histogram)
  const displayColors =
    value.interpolation === 'smooth' ? smoothColorPoints(value.colorPoints) : value.colorPoints
  const displayOpacity =
    value.interpolation === 'smooth'
      ? smoothOpacityPoints(value.opacityPoints)
      : value.opacityPoints

  function updatePoint(target: DragTarget, x: number, y: number) {
    if (!target || !onChange) return
    const next = cloneTransferFunction(value)
    if (target.kind === 'color') {
      next.colorPoints[target.index] = {
        ...next.colorPoints[target.index],
        x: clamp(x),
      }
    } else {
      next.opacityPoints[target.index] = {
        ...next.opacityPoints[target.index],
        x: clamp(x),
        opacity: clamp((92 - y) / 80),
      }
    }
    onChange(next)
  }

  function pointerPosition(event: ReactPointerEvent<SVGSVGElement>) {
    const rect = event.currentTarget.getBoundingClientRect()
    return {
      x: clamp((event.clientX - rect.left) / rect.width),
      y: clamp((event.clientY - rect.top) / rect.height, 0, 1) * 100,
    }
  }

  return (
    <div className="transfer-curve">
      <svg
        viewBox="0 0 100 100"
        role="img"
        aria-label={t('scenePage.transferCurve')}
        onPointerMove={(event) => {
          if (!drag) return
          const position = pointerPosition(event)
          updatePoint(drag, position.x, position.y)
        }}
        onPointerUp={() => setDrag(null)}
        onPointerLeave={() => setDrag(null)}
      >
        <defs>
          <linearGradient id={gradientId} x1="0" x2="1" y1="0" y2="0">
            {displayColors.map((point, index) => (
              <stop
                key={`${point.x}-${index}`}
                offset={`${clamp(point.x) * 100}%`}
                stopColor={point.color}
              />
            ))}
          </linearGradient>
        </defs>
        {histogram.map((count, index) => {
          const width = 100 / Math.max(1, histogram.length)
          const height = (count / maxBar) * 78
          return (
            <rect
              key={index}
              className="transfer-histogram"
              x={index * width}
              y={100 - height}
              width={Math.max(0.2, width - 0.2)}
              height={height}
            />
          )
        })}
        <rect className="transfer-color-band" x="0" y="0" width="100" height="12" fill={`url(#${gradientId})`} />
        <polyline
          className="transfer-opacity-line"
          points={displayOpacity
            .map((point) => `${clamp(point.x) * 100},${opacityY(point.opacity)}`)
            .join(' ')}
        />
        {value.colorPoints.map((point, index) => (
          <circle
            key={`${point.color}-${index}`}
            className="transfer-point transfer-point-color"
            cx={clamp(point.x) * 100}
            cy={9}
            r={2.6}
            fill={point.color}
            role="slider"
            tabIndex={0}
            aria-label={t('scenePage.colorPoint', { index: index + 1 })}
            aria-valuenow={Math.round(point.x * 100)}
            aria-valuemin={0}
            aria-valuemax={100}
            onPointerDown={(event) => {
              event.currentTarget.setPointerCapture(event.pointerId)
              setDrag({ kind: 'color', index })
            }}
            onKeyDown={(event) => {
              const delta = event.shiftKey ? 0.1 : 0.01
              if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
                event.preventDefault()
                const next = cloneTransferFunction(value)
                next.colorPoints[index] = {
                  ...next.colorPoints[index],
                  x: clamp(point.x + (event.key === 'ArrowRight' ? delta : -delta)),
                }
                onChange?.(next)
              }
            }}
          />
        ))}
        {value.opacityPoints.map((point, index) => (
          <circle
            key={`${point.x}-${index}`}
            className="transfer-point transfer-point-opacity"
            cx={clamp(point.x) * 100}
            cy={opacityY(point.opacity)}
            r={2.6}
            role="slider"
            tabIndex={0}
            aria-label={t('scenePage.opacityPoint', { index: index + 1 })}
            aria-valuenow={Math.round(point.opacity * 100)}
            aria-valuemin={0}
            aria-valuemax={100}
            onPointerDown={(event) => {
              event.currentTarget.setPointerCapture(event.pointerId)
              setDrag({ kind: 'opacity', index })
            }}
            onKeyDown={(event) => {
              if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
                event.preventDefault()
                const delta = event.shiftKey ? 0.1 : 0.01
                const next = cloneTransferFunction(value)
                next.opacityPoints[index] = {
                  ...next.opacityPoints[index],
                  x: clamp(point.x + (event.key === 'ArrowRight' ? delta : -delta)),
                }
                onChange?.(next)
              }
              if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
                event.preventDefault()
                const delta = event.shiftKey ? 0.1 : 0.02
                const next = cloneTransferFunction(value)
                next.opacityPoints[index] = {
                  ...next.opacityPoints[index],
                  opacity: clamp(point.opacity + (event.key === 'ArrowUp' ? delta : -delta)),
                }
                onChange?.(next)
              }
            }}
          />
        ))}
      </svg>
      <p className="muted">{t('scenePage.transferHint')}</p>
    </div>
  )
}
