import { useTranslation } from 'react-i18next'
import { Route, Routes } from 'react-router-dom'

import { P01Home } from '../pages/P01Home'
import { P02Import } from '../pages/P02Import'
import { P03Data } from '../pages/P03Data'
import { P04Pipeline } from '../pages/P04Pipeline'
import { P05Charts } from '../pages/P05Charts'
import { P06Scene } from '../pages/P06Scene'
import { P07Reports } from '../pages/P07Reports'
import { P08Providers } from '../pages/P08Providers'
import { P09Trace } from '../pages/P09Trace'
import { P10Settings } from '../pages/P10Settings'
import { AppShell } from './AppShell'

function NotFound() {
  const { t } = useTranslation()

  return (
    <section role="alert" data-testid="page-not-found">
      <h1>{t('notFound.title')}</h1>
      <p className="muted">{t('notFound.description')}</p>
    </section>
  )
}

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<P01Home />} />
        <Route path="projects/:projectId/import" element={<P02Import />} />
        <Route path="projects/:projectId/data" element={<P03Data />} />
        <Route path="projects/:projectId/pipeline" element={<P04Pipeline />} />
        <Route path="projects/:projectId/charts" element={<P05Charts />} />
        <Route path="projects/:projectId/scene" element={<P06Scene />} />
        <Route path="projects/:projectId/reports" element={<P07Reports />} />
        <Route path="settings/providers" element={<P08Providers />} />
        <Route path="projects/:projectId/trace" element={<P09Trace />} />
        <Route path="settings" element={<P10Settings />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
