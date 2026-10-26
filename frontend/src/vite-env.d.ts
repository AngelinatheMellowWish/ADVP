/// <reference types="vite/client" />

declare module '*.geojson' {
  const value: { type: string; features: unknown[]; [key: string]: unknown }
  export default value
}

declare module '@kitware/vtk.js/Rendering/Profiles/Geometry'
declare module '@kitware/vtk.js/Rendering/Profiles/Volume'
declare module '@kitware/vtk.js/Filters/General/ImageMarchingCubes'

