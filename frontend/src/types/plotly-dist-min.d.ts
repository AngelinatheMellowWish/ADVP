declare module 'plotly.js-dist-min' {
  type PlotlyFigure = {
    data: unknown[]
    layout?: Record<string, unknown>
  }

  export function react(
    root: HTMLElement,
    data: unknown[],
    layout?: Record<string, unknown>,
    config?: Record<string, unknown>,
  ): Promise<unknown>

  export function purge(root: HTMLElement): void

  export function downloadImage(
    root: HTMLElement,
    options?: Record<string, unknown>,
  ): Promise<string>

  const Plotly: {
    react: typeof react
    purge: typeof purge
    downloadImage: typeof downloadImage
  }

  export default Plotly
  export type { PlotlyFigure }
}
