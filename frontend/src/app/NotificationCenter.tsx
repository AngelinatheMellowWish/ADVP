import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useNotifications } from './notificationContext'

function BellIcon() {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      height="16"
      viewBox="0 0 24 24"
      width="16"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.8"
    >
      <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" />
      <path d="M10 21h4" />
    </svg>
  )
}

export function NotificationCenter() {
  const { t, i18n } = useTranslation()
  const {
    notifications,
    unreadCount,
    markRead,
    markAllRead,
    clear,
  } = useNotifications()
  const [open, setOpen] = useState(false)
  const centerRef = useRef<HTMLDivElement>(null)

  const toasts = useMemo(
    () => notifications.filter((notification) => !notification.read).slice(0, 3),
    [notifications],
  )

  useEffect(() => {
    if (!open) return

    function handlePointerDown(event: MouseEvent) {
      if (centerRef.current && !centerRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault()
        setOpen(false)
      }
    }

    document.addEventListener('mousedown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [open])

  function formatTime(value: string): string {
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return ''
    return date.toLocaleString(i18n.language)
  }

  return (
    <>
      <div className="toast-region" role="status" aria-live="polite">
        {toasts.map((notification) => (
          <div className={`toast toast-${notification.level}`} key={notification.id}>
            <div className="toast-content">
              {notification.title ? (
                <strong className="toast-title">{notification.title}</strong>
              ) : null}
              <span>{notification.message}</span>
            </div>
            <button
              className="toast-close"
              type="button"
              aria-label={t('notifications.dismiss')}
              onClick={() => markRead(notification.id)}
            >
              ×
            </button>
          </div>
        ))}
      </div>
      <div className="notification-center" ref={centerRef}>
        <button
          className="btn icon-btn notification-bell"
          type="button"
          aria-label={t('notifications.open')}
          aria-haspopup="dialog"
          aria-expanded={open}
          onClick={() => setOpen((current) => !current)}
        >
          <BellIcon />
          {unreadCount > 0 ? (
            <span className="notification-badge" aria-hidden="true">
              {unreadCount > 99 ? '99+' : unreadCount}
            </span>
          ) : null}
        </button>
        {open ? (
          <div
            className="notification-panel"
            role="dialog"
            aria-label={t('notifications.title')}
          >
            <div className="notification-header">
              <h2>{t('notifications.title')}</h2>
              <div className="notification-header-actions">
                <button
                  className="btn"
                  type="button"
                  disabled={unreadCount === 0}
                  onClick={markAllRead}
                >
                  {t('notifications.markAllRead')}
                </button>
                <button
                  className="btn"
                  type="button"
                  disabled={notifications.length === 0}
                  onClick={clear}
                >
                  {t('notifications.clear')}
                </button>
              </div>
            </div>
            {notifications.length === 0 ? (
              <p className="muted notification-empty">{t('notifications.empty')}</p>
            ) : (
              <ul className="notification-list">
                {notifications.map((notification) => (
                  <li
                    className={notification.read ? 'notification-item' : 'notification-item unread'}
                    key={notification.id}
                  >
                    <div className="notification-item-body">
                      {notification.title ? <strong>{notification.title}</strong> : null}
                      <span>{notification.message}</span>
                      <time className="muted notification-time" dateTime={notification.createdAt}>
                        {formatTime(notification.createdAt)}
                      </time>
                    </div>
                    {!notification.read ? (
                      <button
                        className="btn notification-read"
                        type="button"
                        onClick={() => markRead(notification.id)}
                      >
                        {t('notifications.markRead')}
                      </button>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </div>
        ) : null}
      </div>
    </>
  )
}
