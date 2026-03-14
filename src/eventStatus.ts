export function getEventStatusColor(status: string): string {
  switch (status) {
    case 'draft':
      return '#78909c'
    case 'proposed':
      return '#1e88e5'
    case 'planned':
      return '#8e24aa'
    case 'published':
      return '#00897b'
    case 'confirmed':
      return '#43a047'
    case 'canceled':
      return '#e53935'
    case 'completed':
      return '#2e7d32'
    case 'archived':
      return '#546e7a'
    case 'rejected':
      return '#c62828'
    default:
      return '#9e9e9e'
  }
}

export function getEventStatusDisplayLabel(status: string): string {
  return status
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}
