import { useCallback, useMemo, useRef, useState, type ReactNode } from 'react'

import {
  NotificationContext,
  type AppNotification,
  type NotificationInput,
} from './notificationContext'

const MAX_NOTIFICATIONS = 1000
const MAX_AGE_MS = 30 * 24 * 60 * 60 * 1000

function timestampOf(notification: AppNotification): number {
  const value = new Date(notification.createdAt).getTime()
  return Number.isNaN(value) ? Date.now() : value
}

function prune(notifications: AppNotification[]): AppNotification[] {
  const cutoff = Date.now() - MAX_AGE_MS
  return notifications
    .filter((notification) => timestampOf(notification) >= cutoff)
    .slice(0, MAX_NOTIFICATIONS)
}

export function NotificationProvider({ children }: { children: ReactNode }) {
  const [notifications, setNotifications] = useState<AppNotification[]>([])
  const sequence = useRef(0)

  const emit = useCallback((input: NotificationInput): AppNotification => {
    sequence.current += 1
    const createdAt = input.createdAt ?? new Date().toISOString()
    const notification: AppNotification = {
      id: `${Date.now()}-${sequence.current}`,
      title: input.title ?? '',
      message: input.message,
      level: input.level ?? 'info',
      createdAt,
      read: input.read ?? false,
    }
    setNotifications((current) => prune([notification, ...current]))
    return notification
  }, [])

  const markRead = useCallback((id: string) => {
    setNotifications((current) =>
      current.map((notification) =>
        notification.id === id ? { ...notification, read: true } : notification,
      ),
    )
  }, [])

  const markAllRead = useCallback(() => {
    setNotifications((current) =>
      current.map((notification) =>
        notification.read ? notification : { ...notification, read: true },
      ),
    )
  }, [])

  const remove = useCallback((id: string) => {
    setNotifications((current) =>
      current.filter((notification) => notification.id !== id),
    )
  }, [])

  const clear = useCallback(() => {
    setNotifications([])
  }, [])

  const unreadCount = notifications.filter((notification) => !notification.read).length

  const value = useMemo(
    () => ({
      notifications,
      unreadCount,
      emit,
      markRead,
      markAllRead,
      remove,
      clear,
    }),
    [notifications, unreadCount, emit, markRead, markAllRead, remove, clear],
  )

  return (
    <NotificationContext.Provider value={value}>{children}</NotificationContext.Provider>
  )
}
