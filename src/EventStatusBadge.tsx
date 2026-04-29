import { useTranslation } from 'react-i18next'
import styles from './EventStatusBadge.module.css'
import { getEventStatusColor, getEventStatusDisplayLabel } from './eventStatus'

interface EventStatusBadgeProps {
  status?: string | null
  ariaLabel?: string
  className?: string
}

export function EventStatusBadge({ status, ariaLabel, className }: EventStatusBadgeProps) {
  const { t } = useTranslation()

  if (!status) {
    return null
  }

  const label = t(`event.statusValues.${status}`, { defaultValue: getEventStatusDisplayLabel(status) })

  return (
    <span
      className={[styles.statusBadge, className].filter(Boolean).join(' ')}
      style={{ backgroundColor: getEventStatusColor(status) }}
      aria-label={ariaLabel ?? t('event.statusLabel', { status: label })}
      title={label}
    >
      {label}
    </span>
  )
}
