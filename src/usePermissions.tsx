import { useState, useEffect } from 'react'
import { getUserPermissions, type UserPermissions } from './api'

export function usePermissions() {
  const [permissions, setPermissions] = useState<UserPermissions | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const loadPermissions = async () => {
      try {
        const perms = await getUserPermissions()
        setPermissions(perms)
      } catch (error) {
        console.error('Failed to load permissions:', error)
        // Set default unauthenticated permissions
        setPermissions({
          is_authenticated: false,
          is_staff: false,
          is_superuser: false,
          is_active: false,
          permissions: [],
        })
      } finally {
        setLoading(false)
      }
    }

    loadPermissions()
  }, [])

  const hasPermission = (permission: string): boolean => {
    if (!permissions) return false
    if (permissions.is_superuser) return true
    return permissions.permissions.includes(permission)
  }

  const canView = (model: string): boolean => {
    return hasPermission(`view_${model}`) || hasPermission(`change_${model}`) || hasPermission(`add_${model}`)
  }

  const canBrowse = (model: string): boolean => {
    return hasPermission(`browse_${model}`) || canView(model)
  }

  const canAdd = (model: string): boolean => {
    return hasPermission(`add_${model}`)
  }

  const canChange = (model: string): boolean => {
    return hasPermission(`change_${model}`)
  }

  const canDelete = (model: string): boolean => {
    return hasPermission(`delete_${model}`)
  }

  return {
    permissions,
    loading,
    hasPermission,
    canView,
    canBrowse,
    canAdd,
    canChange,
    canDelete,
  }
}
