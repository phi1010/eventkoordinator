import styles from './EventStatusBadge.module.css'
import { getEventStatusColor, getEventStatusDisplayLabel } from './eventStatus'

interface EventStatusBadgeProps {
  status?: string | null
  ariaLabel?: string
  className?: string
}

export function EventStatusBadge({ status, ariaLabel, className }: EventStatusBadgeProps) {
  if (!status) {
    return null
  }

  return (
    <span
      className={[styles.statusBadge, className].filter(Boolean).join(' ')}
      style={{ backgroundColor: getEventStatusColor(status) }}
      aria-label={ariaLabel ?? `Event status: ${status}`}
      title={getEventStatusDisplayLabel(status)}
    >
      {getEventStatusDisplayLabel(status)}
    </span>
  )
}
