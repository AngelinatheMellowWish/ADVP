import { spawnSync } from 'node:child_process'
import { mkdirSync, rmSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const entries = ['plotly', 'echarts', 'cytoscape', 'deckgl', 'vtk']
const scriptsDir = path.dirname(fileURLToPath(import.meta.url))
const frontendDir = path.resolve(scriptsDir, '..')
const distShare = path.join(frontendDir, 'dist-share')
const viteBin = path.join(frontendDir, 'node_modules', 'vite', 'bin', 'vite.js')

rmSync(distShare, { recursive: true, force: true })
mkdirSync(distShare, { recursive: true })

for (const entry of entries) {
  const result = spawnSync(
    process.execPath,
    [viteBin, 'build', '--config', 'vite.share.config.ts'],
    {
      cwd: frontendDir,
      env: { ...process.env, SHARE_ENTRY: entry },
      stdio: 'inherit',
    },
  )
  if (result.status !== 0) {
    process.exit(result.status ?? 1)
  }
}

console.log('share bundles:', entries.map((entry) => `share-${entry}.js`).join(', '))
