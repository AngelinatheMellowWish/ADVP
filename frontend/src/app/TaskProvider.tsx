import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'

import { request } from '../api/projects'
import { TaskContext, type TaskCounts } from './taskContext'

const EMPTY_TASKS: TaskCounts = {
  imports: 0,
  pipelines: 0,
  exports: 0,
  render_jobs: 0,
  live_streams: 0,
}

const POLL_INTERVAL_MS = 3000

function toCount(value: unknown): number {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) {
    return 0
  }
  return Math.floor(value)
}

function normalizeTasks(payload: unknown): TaskCounts {
  const record = payload && typeof payload === 'object' ? (payload as Record<string, unknown>) : {}
  return {
    imports: toCount(record.imports),
    pipelines: toCount(record.pipelines),
    exports: toCount(record.exports),
    render_jobs: toCount(record.render_jobs),
    live_streams: toCount(record.live_streams),
  }
}

function sameTasks(left: TaskCounts, right: TaskCounts): boolean {
  return (
    left.imports === right.imports &&
    left.pipelines === right.pipelines &&
    left.exports === right.exports &&
    left.render_jobs === right.render_jobs &&
    left.live_streams === right.live_streams
  )
}

function totalOf(tasks: TaskCounts): number {
  return (
    tasks.imports +
    tasks.pipelines +
    tasks.exports +
    tasks.render_jobs +
    tasks.live_streams
  )
}

export function TaskProvider({ children }: { children: ReactNode }) {
  const [tasks, setTasks] = useState<TaskCounts>(EMPTY_TASKS)
  const [error, setError] = useState(false)
  const mounted = useRef(false)
  const controllerRef = useRef<AbortController | null>(null)
  const intervalRef = useRef<number | null>(null)

  const load = useCallback(() => {
    if (!mounted.current || controllerRef.current) return
    const controller = new AbortController()
    controllerRef.current = controller
    request<unknown>('/api/system/tasks', { signal: controller.signal })
      .then((payload) => {
        if (controller.signal.aborted || !mounted.current) return
        const next = normalizeTasks(payload)
        setTasks((current) => (sameTasks(current, next) ? current : next))
        setError(false)
      })
      .catch(() => {
        if (controller.signal.aborted || !mounted.current) return
        setError(true)
      })
      .finally(() => {
        if (controllerRef.current === controller) {
          controllerRef.current = null
        }
      })
  }, [])

  const stopPolling = useCallback(() => {
    if (intervalRef.current === null) return
    window.clearInterval(intervalRef.current)
    intervalRef.current = null
  }, [])

  const startPolling = useCallback(() => {
    if (intervalRef.current !== null) return
    intervalRef.current = window.setInterval(load, POLL_INTERVAL_MS)
  }, [load])

  const refresh = useCallback(() => {
    load()
  }, [load])

  useEffect(() => {
    mounted.current = true

    function syncPolling() {
      if (document.visibilityState === 'hidden') {
        stopPolling()
        return
      }
      load()
      startPolling()
    }

    syncPolling()
    document.addEventListener('visibilitychange', syncPolling)
    return () => {
      mounted.current = false
      stopPolling()
      document.removeEventListener('visibilitychange', syncPolling)
      controllerRef.current?.abort()
      controllerRef.current = null
    }
  }, [load, startPolling, stopPolling])

  const value = useMemo(
    () => ({ tasks, total: totalOf(tasks), error, refresh }),
    [tasks, error, refresh],
  )

  return <TaskContext.Provider value={value}>{children}</TaskContext.Provider>
}
