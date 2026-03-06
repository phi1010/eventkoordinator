import { useEffect, useCallback } from 'react'

export interface UnsavedChangesHook {
  hasUnsavedChanges: boolean
  confirmNavigation: () => Promise<boolean>
}

const UNSAVED_CHANGES_MESSAGE =
  'You have unsaved changes. Are you sure you want to leave without saving?'

export function useUnsavedChanges(hasChanges: boolean): UnsavedChangesHook {
  const confirmNavigation = useCallback(async (): Promise<boolean> => {
    if (!hasChanges) {
      return true
    }

    return window.confirm(UNSAVED_CHANGES_MESSAGE)
  }, [hasChanges])

  // Guard browser back/forward navigation while there are unsaved changes.
  useEffect(() => {
    if (!hasChanges) {
      return
    }

    // Insert a guard entry so the first Back press can be intercepted.
    window.history.pushState({ unsavedChangesGuard: true }, '', window.location.href)

    const handlePopState = () => {
      const confirmed = window.confirm(UNSAVED_CHANGES_MESSAGE)

      if (confirmed) {
        // Remove this handler before moving back so we don't re-prompt.
        window.removeEventListener('popstate', handlePopState)
        window.history.back()
        return
      }

      // Reinsert guard entry and keep user on the current page.
      window.history.pushState({ unsavedChangesGuard: true }, '', window.location.href)
    }

    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [hasChanges])

  // Warn before browser close/refresh
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (hasChanges) {
        e.preventDefault()
        e.returnValue = ''
      }
    }

    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => window.removeEventListener('beforeunload', handleBeforeUnload)
  }, [hasChanges])

  return {
    hasUnsavedChanges: hasChanges,
    confirmNavigation,
  }
}
