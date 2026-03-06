import { useRef, useEffect, useState } from 'react'
import styles from './ContentRenderer.module.css'
import { EventEditor } from './EventEditor'
import { SeriesGeneralEditor } from './SeriesGeneralEditor'
import { checkObjectPermission, type Event, type Series } from './api'

interface ContentRendererProps {
  series: Series
  selectedEventId: string
  onSeriesUpdate: (updated: Series) => void
  onEventUpdate: (updated: Event) => void
  onRequestNavigation?: (confirmFn: () => Promise<boolean>) => void
  canEditSeries?: boolean
  canEditEvent?: boolean
}

export function ContentRenderer({ series, selectedEventId, onSeriesUpdate, onEventUpdate, onRequestNavigation, canEditSeries = true, canEditEvent = true }: ContentRendererProps) {
  const selectedEvent = series.events.find((e) => e.id === selectedEventId)
  const isGeneralInfo = selectedEventId === 'general'
  const confirmNavigationRef = useRef<(() => Promise<boolean>) | null>(null)
  const [canViewSelectedObject, setCanViewSelectedObject] = useState<boolean | null>(null)
  const [canEditSelectedObject, setCanEditSelectedObject] = useState<boolean | null>(null)
  const [permissionLoading, setPermissionLoading] = useState(false)

  useEffect(() => {
    const checkPermissions = async () => {
      if (isGeneralInfo) {
        setPermissionLoading(true)
        try {
          const [canView, canChange] = await Promise.all([
            checkObjectPermission({
              app: 'apiv1',
              action: 'view',
              object_type: 'series',
              object_id: series.id,
            }),
            checkObjectPermission({
              app: 'apiv1',
              action: 'change',
              object_type: 'series',
              object_id: series.id,
            }),
          ])
          setCanViewSelectedObject(canView)
          setCanEditSelectedObject(canEditSeries && canChange)
        } finally {
          setPermissionLoading(false)
        }
        return
      }

      if (selectedEvent) {
        setPermissionLoading(true)
        try {
          const [canView, canChange] = await Promise.all([
            checkObjectPermission({
              app: 'apiv1',
              action: 'view',
              object_type: 'event',
              object_id: selectedEvent.id,
            }),
            checkObjectPermission({
              app: 'apiv1',
              action: 'change',
              object_type: 'event',
              object_id: selectedEvent.id,
            }),
          ])
          setCanViewSelectedObject(canView)
          setCanEditSelectedObject(canEditEvent && canChange)
        } finally {
          setPermissionLoading(false)
        }
        return
      }

      setCanViewSelectedObject(null)
      setCanEditSelectedObject(null)
    }

    void checkPermissions()
  }, [canEditEvent, canEditSeries, isGeneralInfo, selectedEvent, series.id])

  const handleRequestNavigation = (confirmFn: () => Promise<boolean>) => {
    confirmNavigationRef.current = confirmFn
    if (onRequestNavigation) {
      onRequestNavigation(confirmFn)
    }
  }

  return (
    <>
      <h1>{series.name}</h1>
      {permissionLoading ? (
        <div className={styles.placeholder}>
          <p>Checking permissions...</p>
        </div>
      ) : isGeneralInfo ? (
        canViewSelectedObject ? (
          <SeriesGeneralEditor
            series={series}
            onSeriesUpdate={onSeriesUpdate}
            onRequestNavigation={handleRequestNavigation}
            disabled={!canEditSelectedObject}
          />
        ) : (
          <div className={styles.placeholder}>
            <p>You do not have permission to view this series.</p>
          </div>
        )
      ) : selectedEvent ? (
        canViewSelectedObject ? (
          <EventEditor
            series={series}
            event={selectedEvent}
            onEventUpdate={onEventUpdate}
            onRequestNavigation={handleRequestNavigation}
            disabled={!canEditSelectedObject}
          />
        ) : (
          <div className={styles.placeholder}>
            <p>You do not have permission to view this event.</p>
          </div>
        )
      ) : (
        <div className={styles.placeholder}>
          <p>Loading...</p>
        </div>
      )}
    </>
  )
}
