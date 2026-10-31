import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { useParams } from 'react-router-dom'

import { errorMessage, getProject, type ProjectDetail } from '../api/projects'
import { ProjectContext } from './projectContext'

type ProjectError = {
  projectId: string
  message: string
}

export function ProjectProvider({ children }: { children: ReactNode }) {
  const { projectId } = useParams<{ projectId?: string }>()
  const [project, setProject] = useState<ProjectDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<ProjectError | null>(null)
  const [reloadToken, setReloadToken] = useState(0)

  const refresh = useCallback(() => {
    setReloadToken((token) => token + 1)
  }, [])

  useEffect(() => {
    if (!projectId) {
      setProject(null)
      setLoading(false)
      setError(null)
      return
    }

    let cancelled = false
    setProject((current) => (current?.id === projectId ? current : null))
    setLoading(true)
    setError(null)

    getProject(projectId)
      .then((data) => {
        if (!cancelled) {
          setProject(data)
          setLoading(false)
          setError(null)
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setProject(null)
          setError({ projectId, message: errorMessage(caught) })
          setLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [projectId, reloadToken])

  const visibleProject = project && project.id === projectId ? project : null
  const visibleError = error && error.projectId === projectId ? error.message : null
  const visibleLoading =
    Boolean(projectId) && (loading || (visibleProject === null && visibleError === null))

  const value = useMemo(
    () => ({
      project: visibleProject,
      loading: visibleLoading,
      error: visibleError,
      refresh,
    }),
    [visibleProject, visibleLoading, visibleError, refresh],
  )

  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>
}
