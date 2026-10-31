import { createContext, useContext } from 'react'

export type NotificationLevel = 'info' | 'success' | 'warning' | 'error'

export type AppNotification = {
  id: string
  title: string
  message: string
  level: NotificationLevel
  createdAt: string
  read: boolean
}

export type NotificationInput = {
  title?: string
  message: string
  level?: NotificationLevel
  createdAt?: string
  read?: boolean
}

export type NotificationContextValue = {
  notifications: AppNotification[]
  unreadCount: number
  emit: (input: NotificationInput) => AppNotification
  markRead: (id: string) => void
  markAllRead: () => void
  remove: (id: string) => void
  clear: () => void
}

export const NotificationContext = createContext<NotificationContextValue | null>(null)

export function useNotifications(): NotificationContextValue {
  const value = useContext(NotificationContext)
  if (!value) {
    throw new Error('useNotifications must be used within NotificationProvider')
  }
  return value
}
