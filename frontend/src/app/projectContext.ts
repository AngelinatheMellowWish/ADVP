import { createContext, useContext } from 'react'

import type { ProjectDetail } from '../api/projects'

export type ProjectContextValue = {
  project: ProjectDetail | null
  loading: boolean
  error: string | null
  refresh: () => void
}

export const ProjectContext = createContext<ProjectContextValue | null>(null)

export function useProject(): ProjectContextValue {
  const value = useContext(ProjectContext)
  if (!value) {
    throw new Error('useProject must be used within ProjectProvider')
  }
  return value
}
