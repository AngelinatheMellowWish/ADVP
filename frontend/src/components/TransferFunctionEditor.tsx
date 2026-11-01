import { useTranslation } from 'react-i18next'

import type { SceneTransferFunction } from '../api/scenes'
import {
  cloneTransferFunction,
  sortTransferFunction,
  TRANSFER_PRESETS,
} from '../state/transferFunction'
import { TransferCurve } from './TransferCurve'

const PRESETS = ['viridis', 'grayscale', 'hot', 'jet'] as const

function largestGap(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b)
  let bestStart = sorted[0] ?? 0
  let bestGap = -1
  for (let index = 0; index < sorted.length - 1; index += 1) {
    const gap = sorted[index + 1] - sorted[index]
    if (gap > bestGap) {
      bestGap = gap
      bestStart = sorted[index]
    }
  }
  return bestStart + Math.max(0, bestGap) / 2
}

export function TransferFunctionEditor({
  value,
  onChange,
  histogram = [],
}: {
  value: SceneTransferFunction
  onChange: (next: SceneTransferFunction) => void
  histogram?: number[]
}) {
  const { t } = useTranslation()

  function addColorPoint() {
    const next = cloneTransferFunction(value)
    const x = largestGap(next.colorPoints.map((point) => point.x))
    const nearest = [...next.colorPoints].sort((a, b) => a.x - b.x).at(-1)
    next.colorPoints.push({ x, color: nearest?.color ?? '#ffffff' })
    onChange(sortTransferFunction(next))
  }

  function addOpacityPoint() {
    const next = cloneTransferFunction(value)
    const x = largestGap(next.opacityPoints.map((point) => point.x))
    const before = [...next.opacityPoints]
      .sort((a, b) => a.x - b.x)
      .filter((point) => point.x <= x)
      .at(-1)
    next.opacityPoints.push({ x, opacity: before?.opacity ?? 0.5 })
    onChange(sortTransferFunction(next))
  }

  function removeColorPoint(index: number) {
    if (value.colorPoints.length <= 2) return
    const next = cloneTransferFunction(value)
    next.colorPoints.splice(index, 1)
    onChange(next)
  }

  function removeOpacityPoint(index: number) {
    if (value.opacityPoints.length <= 2) return
    const next = cloneTransferFunction(value)
    next.opacityPoints.splice(index, 1)
    onChange(next)
  }

  return (
    <section
      className="card transfer-function-editor"
      aria-label={t('scenePage.transferFunction')}
      data-testid="transfer-function-editor"
    >
      <div className="panel-title">
        <div>
          <h2>{t('scenePage.transferFunction')}</h2>
          <p className="muted">{t('scenePage.transferDescription')}</p>
        </div>
        <label>
          {t('scenePage.interpolation')}
          <select
            className="input"
            value={value.interpolation}
            onChange={(event) =>
              onChange({
                ...cloneTransferFunction(value),
                interpolation: event.target.value === 'smooth' ? 'smooth' : 'linear',
              })
            }
          >
            <option value="linear">{t('scenePage.linear')}</option>
            <option value="smooth">{t('scenePage.smooth')}</option>
          </select>
        </label>
      </div>

      <TransferCurve value={value} histogram={histogram} onChange={onChange} />

      <div className="transfer-actions">
        <button className="btn" type="button" onClick={addColorPoint}>
          {t('scenePage.addColorPoint')}
        </button>
        <button className="btn" type="button" onClick={addOpacityPoint}>
          {t('scenePage.addOpacityPoint')}
        </button>
        {PRESETS.map((preset) => (
          <button
            key={preset}
            className="btn"
            type="button"
            onClick={() => onChange(cloneTransferFunction(TRANSFER_PRESETS[preset]))}
          >
            {t(`scenePage.presets.${preset}`)}
          </button>
        ))}
      </div>

      <div className="transfer-points">
        <div>
          <h3>{t('scenePage.colorPoints')}</h3>
          <ul>
            {value.colorPoints.map((point, index) => (
              <li key={`color-${index}`}>
                <input
                  className="input"
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  aria-label={t('scenePage.colorPointPosition', { index: index + 1 })}
                  value={point.x}
                  onChange={(event) => {
                    const next = cloneTransferFunction(value)
                    next.colorPoints[index] = { ...point, x: Number(event.target.value) }
                    onChange(sortTransferFunction(next))
                  }}
                />
                <input
                  type="color"
                  aria-label={t('scenePage.colorPointColor', { index: index + 1 })}
                  value={point.color}
                  onChange={(event) => {
                    const next = cloneTransferFunction(value)
                    next.colorPoints[index] = { ...point, color: event.target.value }
                    onChange(next)
                  }}
                />
                <button
                  className="btn"
                  type="button"
                  aria-label={t('scenePage.removeColorPoint', { index: index + 1 })}
                  onClick={() => removeColorPoint(index)}
                  disabled={value.colorPoints.length <= 2}
                >
                  {t('scenePage.removePoint')}
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div>
          <h3>{t('scenePage.opacityPoints')}</h3>
          <ul>
            {value.opacityPoints.map((point, index) => (
              <li key={`opacity-${index}`}>
                <input
                  className="input"
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  aria-label={t('scenePage.opacityPointPosition', { index: index + 1 })}
                  value={point.x}
                  onChange={(event) => {
                    const next = cloneTransferFunction(value)
                    next.opacityPoints[index] = { ...point, x: Number(event.target.value) }
                    onChange(sortTransferFunction(next))
                  }}
                />
                <input
                  className="input"
                  type="range"
                  min="0"
                  max="1"
                  step="0.01"
                  aria-label={t('scenePage.opacityPointValue', { index: index + 1 })}
                  value={point.opacity}
                  onChange={(event) => {
                    const next = cloneTransferFunction(value)
                    next.opacityPoints[index] = {
                      ...point,
                      opacity: Number(event.target.value),
                    }
                    onChange(next)
                  }}
                />
                <span className="muted">{point.opacity.toFixed(2)}</span>
                <button
                  className="btn"
                  type="button"
                  aria-label={t('scenePage.removeOpacityPoint', { index: index + 1 })}
                  onClick={() => removeOpacityPoint(index)}
                  disabled={value.opacityPoints.length <= 2}
                >
                  {t('scenePage.removePoint')}
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  )
}
