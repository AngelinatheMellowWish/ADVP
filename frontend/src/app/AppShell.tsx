import { Outlet } from 'react-router-dom'

import '../i18n'
import { CommandPalette } from './CommandPalette'
import { NotificationProvider } from './NotificationProvider'
import { ProjectProvider } from './ProjectProvider'
import { Sidebar } from './Sidebar'
import { TaskBar } from './TaskBar'
import { TaskProvider } from './TaskProvider'
import { Topbar } from './Topbar'

export function AppShell() {
  return (
    <ProjectProvider>
      <TaskProvider>
        <NotificationProvider>
          <div className="app-shell">
            <Sidebar />
            <Topbar />
            <main className="page">
              <Outlet />
            </main>
            <TaskBar />
            <CommandPalette />
          </div>
        </NotificationProvider>
      </TaskProvider>
    </ProjectProvider>
  )
}
