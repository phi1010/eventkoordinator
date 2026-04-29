import { useTranslation } from 'react-i18next'
import { useState } from 'react'

import styles from './ImageUploadField.module.css'

interface ImageUploadFieldProps {
  label: string
  inputId: string
  previewAlt: string
  currentImageUrl?: string | null
  helpText?: string
  emptyText?: string
  disabled?: boolean
  isUploading?: boolean
  uploadProgress?: number | null
  error?: string | null
  onFileSelected: (file: File) => void | Promise<void>
}

export function ImageUploadField({
  label,
  inputId,
  previewAlt,
  currentImageUrl,
  helpText,
  emptyText,
  disabled = false,
  isUploading = false,
  uploadProgress = null,
  error = null,
  onFileSelected,
}: ImageUploadFieldProps) {
  const { t } = useTranslation()
  const [isLocallyUploading, setIsLocallyUploading] = useState(false)

  const effectiveEmptyText = emptyText ?? t('common.noImageUploaded')
  const effectiveHelpText = helpText

  const handleChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''

    if (!file) {
      return
    }

    try {
      setIsLocallyUploading(true)
      await onFileSelected(file)
    } finally {
      setIsLocallyUploading(false)
    }
  }

  const shouldShowProgress = isLocallyUploading || isUploading

  return (
    <div className={styles.container}>
      <div className={styles.previewBox}>
        {currentImageUrl ? (
          <img src={currentImageUrl} alt={previewAlt} className={styles.previewImage} />
        ) : (
          <div className={styles.emptyPreview}>{effectiveEmptyText}</div>
        )}
      </div>

      <div className={styles.controls}>
        <label htmlFor={inputId} className={styles.label}>
          {label}
        </label>
        <input
          id={inputId}
          type="file"
          accept="image/png,image/jpeg"
          onChange={handleChange}
          disabled={disabled || shouldShowProgress}
          className={styles.fileInput}
        />
        {effectiveHelpText && <small className={styles.helpText}>{effectiveHelpText}</small>}
        {shouldShowProgress && (
          <div className={styles.progressWrapper}>
            <progress
              max={100}
              value={uploadProgress ?? undefined}
              aria-label={`${label} ${t('common.uploadProgress')}`}
              className={styles.progressNative}
            />
            <span className={styles.progressText} aria-live="polite">
              {uploadProgress !== null ? t('common.uploadingProgress', { percent: uploadProgress }) : t('common.uploading')}
            </span>
          </div>
        )}
        {error && (
          <div className={styles.errorText} role="alert">
            {error}
          </div>
        )}
      </div>
    </div>
  )
}

