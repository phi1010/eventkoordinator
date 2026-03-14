import { useState } from 'react'
import {
  addSpeakerToProposal,
  removeSpeaker,
  uploadSpeakerImage,
  updateSpeaker,
  type ProposalSpeakerOut,
  type SpeakerIn,
} from './api'
import { ImageUploadField } from './ImageUploadField'
import styles from './SpeakerListEditor.module.css'

interface SpeakerListEditorProps {
  proposalId: string
  speakers: ProposalSpeakerOut[]
  onSpeakersChange: (speakers: ProposalSpeakerOut[]) => void
  disabled?: boolean
}

interface EditingSpeaker {
  id: string
  email: string
  display_name: string
  biography: string
  use_gravatar: boolean
}

interface UploadState {
  isUploading: boolean
  progress: number | null
  error: string | null
}

function getSpeakerFieldId(prefix: string, speakerId: string, fieldName: string) {
  return `${prefix}-${speakerId}-${fieldName}`
}

export function SpeakerListEditor({
  proposalId,
  speakers,
  onSpeakersChange,
  disabled = false,
}: SpeakerListEditorProps) {
  const [newSpeaker, setNewSpeaker] = useState<SpeakerIn>({
    email: '',
    display_name: '',
    biography: '',
    use_gravatar: false,
  })
  const [editingSpeaker, setEditingSpeaker] = useState<EditingSpeaker | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [uploadStates, setUploadStates] = useState<Record<string, UploadState>>({})

  const getUploadState = (speakerId: string): UploadState => (
    uploadStates[speakerId] ?? {
      isUploading: false,
      progress: null,
      error: null,
    }
  )

  const updateUploadState = (speakerId: string, updates: Partial<UploadState>) => {
    setUploadStates((previous) => ({
      ...previous,
      [speakerId]: {
        ...(previous[speakerId] ?? {
          isUploading: false,
          progress: null,
          error: null,
        }),
        ...updates,
      },
    }))
  }

  const handleAddSpeaker = async () => {
    if (!newSpeaker.email?.trim()) {
      setError('Email is required')
      return
    }

    try {
      setIsSaving(true)
      setError(null)

      const addedSpeaker = await addSpeakerToProposal(proposalId, newSpeaker)
      onSpeakersChange([...speakers, addedSpeaker])

      // Reset form
      setNewSpeaker({
        email: '',
        display_name: '',
        biography: '',
        use_gravatar: false,
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add speaker')
    } finally {
      setIsSaving(false)
    }
  }

  const handleEditSpeaker = (speaker: ProposalSpeakerOut) => {
    setEditingSpeaker({
      id: speaker.id,
      email: speaker.speaker.email,
      display_name: speaker.speaker.display_name,
      biography: speaker.speaker.biography,
      use_gravatar: speaker.speaker.use_gravatar,
    })
    setError(null)
  }

  const handleSaveEdit = async () => {
    if (!editingSpeaker) return

    try {
      setIsSaving(true)
      setError(null)

      const updatedSpeaker = await updateSpeaker(proposalId, editingSpeaker.id, {
        email: editingSpeaker.email,
        display_name: editingSpeaker.display_name,
        biography: editingSpeaker.biography,
        use_gravatar: editingSpeaker.use_gravatar,
      })

      onSpeakersChange(
        speakers.map((s) => (s.id === editingSpeaker.id ? updatedSpeaker : s))
      )
      setEditingSpeaker(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update speaker')
    } finally {
      setIsSaving(false)
    }
  }

  const handleRemoveSpeaker = async (speakerId: string) => {
    try {
      setIsSaving(true)
      setError(null)

      await removeSpeaker(proposalId, speakerId)
      onSpeakersChange(speakers.filter((s) => s.id !== speakerId))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to remove speaker')
    } finally {
      setIsSaving(false)
    }
  }

  const handleSpeakerImageUpload = async (speaker: ProposalSpeakerOut, file: File) => {
    try {
      updateUploadState(speaker.id, {
        isUploading: true,
        progress: 0,
        error: null,
      })

      const updatedSpeaker = await uploadSpeakerImage(
        proposalId,
        speaker.id,
        file,
        (progress) => updateUploadState(speaker.id, { progress })
      )

      onSpeakersChange(
        speakers.map((currentSpeaker) => (
          currentSpeaker.id === speaker.id ? updatedSpeaker : currentSpeaker
        ))
      )
    } catch (err) {
      updateUploadState(speaker.id, {
        error: err instanceof Error ? err.message : 'Failed to upload speaker image',
      })
    } finally {
      updateUploadState(speaker.id, {
        isUploading: false,
        progress: null,
      })
    }
  }

  return (
    <div style={{ marginBottom: '2rem' }}>
      <h3 className={styles.title}>Speakers</h3>

      {error && (
        <div className={styles.errorBox}>
          {error}
        </div>
      )}

      {/* Speaker List */}
      {speakers.length > 0 && (
        <div style={{ marginBottom: '1.5rem' }}>
          <h4 className={styles.speakerListHeader}>
            Added Speakers ({speakers.length})
          </h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {speakers.map((speaker) =>
              editingSpeaker?.id === speaker.id ? (
                // Edit Mode
                <div key={speaker.id} className={styles.editCard}>
                  <div style={{ marginBottom: '1rem' }}>
                    <ImageUploadField
                      label="Speaker image"
                      inputId={`speaker-image-${speaker.id}`}
                      previewAlt={`Speaker image preview for ${speaker.speaker.display_name || speaker.speaker.email}`}
                      currentImageUrl={speaker.speaker.profile_picture || null}
                      disabled={disabled || isSaving}
                      isUploading={getUploadState(speaker.id).isUploading}
                      uploadProgress={getUploadState(speaker.id).progress}
                      error={getUploadState(speaker.id).error}
                      helpText="Upload a JPG or PNG image up to 10 MB for this speaker."
                      onFileSelected={(file) => handleSpeakerImageUpload(speaker, file)}
                    />
                  </div>

                  <div style={{ marginBottom: '0.75rem' }}>
                    <label
                      htmlFor={getSpeakerFieldId('edit-speaker', speaker.id, 'email')}
                      style={{ display: 'block', marginBottom: '0.25rem', fontSize: '0.9rem' }}
                    >
                      Email:
                    </label>
                    <input
                      id={getSpeakerFieldId('edit-speaker', speaker.id, 'email')}
                      type="email"
                      value={editingSpeaker.email}
                      onChange={(e) =>
                        setEditingSpeaker({ ...editingSpeaker, email: e.target.value })
                      }
                      disabled={disabled || isSaving}
                      className={styles.formInput}
                    />
                  </div>

                  <div style={{ marginBottom: '0.75rem' }}>
                    <label
                      htmlFor={getSpeakerFieldId('edit-speaker', speaker.id, 'display-name')}
                      style={{ display: 'block', marginBottom: '0.25rem', fontSize: '0.9rem' }}
                    >
                      Display Name:
                    </label>
                    <input
                      id={getSpeakerFieldId('edit-speaker', speaker.id, 'display-name')}
                      type="text"
                      value={editingSpeaker.display_name}
                      onChange={(e) =>
                        setEditingSpeaker({ ...editingSpeaker, display_name: e.target.value })
                      }
                      disabled={disabled || isSaving}
                      className={styles.formInput}
                    />
                    <small className={styles.helpText}>
                      e.g., John Doe
                    </small>
                  </div>

                  <div style={{ marginBottom: '0.75rem' }}>
                    <label
                      htmlFor={getSpeakerFieldId('edit-speaker', speaker.id, 'biography')}
                      style={{ display: 'block', marginBottom: '0.25rem', fontSize: '0.9rem' }}
                    >
                      Biography:
                    </label>
                    <textarea
                      id={getSpeakerFieldId('edit-speaker', speaker.id, 'biography')}
                      value={editingSpeaker.biography}
                      onChange={(e) =>
                        setEditingSpeaker({ ...editingSpeaker, biography: e.target.value })
                      }
                      disabled={disabled || isSaving}
                      rows={3}
                      className={styles.formInput}
                      style={{ overflow: 'auto', wordBreak: 'break-word', overflowWrap: 'break-word' }}
                    />
                    <small className={styles.helpText}>
                      Brief speaker biography (minimum 50 characters recommended)
                    </small>
                  </div>

                  <label
                    htmlFor={getSpeakerFieldId('edit-speaker', speaker.id, 'use-gravatar')}
                    style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.9rem' }}
                  >
                    <input
                      id={getSpeakerFieldId('edit-speaker', speaker.id, 'use-gravatar')}
                      type="checkbox"
                      checked={editingSpeaker.use_gravatar}
                      onChange={(e) =>
                        setEditingSpeaker({ ...editingSpeaker, use_gravatar: e.target.checked })
                      }
                      disabled={disabled || isSaving}
                    />
                    Use Gravatar for profile picture
                  </label>

                  <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem' }}>
                    <button
                      type="button"
                      onClick={handleSaveEdit}
                      disabled={disabled || isSaving}
                      style={{
                        padding: '0.5rem 1rem',
                        backgroundColor: '#4caf50',
                        color: 'white',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: 'pointer',
                        fontSize: '0.9rem',
                      }}
                    >
                      {isSaving ? 'Saving...' : 'Save'}
                    </button>
                    <button
                      type="button"
                      onClick={() => setEditingSpeaker(null)}
                      disabled={disabled || isSaving}
                      style={{
                        padding: '0.5rem 1rem',
                        backgroundColor: '#666',
                        color: 'white',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: 'pointer',
                        fontSize: '0.9rem',
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                // Display Mode
                <div key={speaker.id} className={styles.speakerCard}>
                  {speaker.speaker.profile_picture && (
                    <img
                      src={speaker.speaker.profile_picture}
                      alt={`Speaker image preview for ${speaker.speaker.display_name || speaker.speaker.email}`}
                      className={styles.speakerImage}
                    />
                  )}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className={styles.speakerName}>
                      {speaker.speaker.display_name || speaker.speaker.email}
                    </div>
                    <div className={styles.speakerEmail}>
                      {speaker.speaker.email}
                    </div>
                    <div className={styles.speakerBio}>
                      {speaker.speaker.biography}
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: '0.5rem', marginLeft: '1rem', flexShrink: 0 }}>
                    <button
                      type="button"
                      onClick={() => handleEditSpeaker(speaker)}
                      disabled={disabled || isSaving}
                      style={{
                        padding: '0.4rem 0.8rem',
                        backgroundColor: disabled || isSaving ? '#9e9e9e' : '#2196f3',
                        color: 'white',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: disabled || isSaving ? 'not-allowed' : 'pointer',
                        fontSize: '0.85rem',
                        flexShrink: 0,
                        opacity: disabled || isSaving ? 0.7 : 1,
                      }}
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      onClick={() => handleRemoveSpeaker(speaker.id)}
                      disabled={disabled || isSaving}
                      style={{
                        padding: '0.4rem 0.8rem',
                        backgroundColor: disabled || isSaving ? '#9e9e9e' : '#f44336',
                        color: 'white',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: disabled || isSaving ? 'not-allowed' : 'pointer',
                        fontSize: '0.85rem',
                        flexShrink: 0,
                        opacity: disabled || isSaving ? 0.7 : 1,
                      }}
                    >
                      Remove
                    </button>
                  </div>
                </div>
              )
            )}
          </div>
        </div>
      )}

      {/* Add New Speaker Form */}
      {!editingSpeaker && (
        <div className={styles.addForm}>
          <h4 className={styles.addFormHeader}>
            Add New Speaker
          </h4>

          <div style={{ marginBottom: '0.75rem' }}>
            <label htmlFor="new-speaker-email" style={{ display: 'block', marginBottom: '0.25rem', fontSize: '0.9rem' }}>
              Email (required):
            </label>
            <input
              id="new-speaker-email"
              type="email"
              value={newSpeaker.email || ''}
              onChange={(e) => setNewSpeaker({ ...newSpeaker, email: e.target.value })}
              disabled={disabled || isSaving}
              className={styles.formInput}
            />
            <small className={styles.helpText}>
              e.g., john@example.com
            </small>
          </div>

          <div style={{ marginBottom: '0.75rem' }}>
            <label htmlFor="new-speaker-display-name" style={{ display: 'block', marginBottom: '0.25rem', fontSize: '0.9rem' }}>
              Display Name:
            </label>
            <input
              id="new-speaker-display-name"
              type="text"
              value={newSpeaker.display_name || ''}
              onChange={(e) => setNewSpeaker({ ...newSpeaker, display_name: e.target.value })}
              disabled={disabled || isSaving}
              className={styles.formInput}
            />
            <small className={styles.helpText}>
              e.g., John Doe
            </small>
          </div>

          <div style={{ marginBottom: '0.75rem' }}>
            <label htmlFor="new-speaker-biography" style={{ display: 'block', marginBottom: '0.25rem', fontSize: '0.9rem' }}>
              Biography:
            </label>
            <textarea
              id="new-speaker-biography"
              value={newSpeaker.biography || ''}
              onChange={(e) => setNewSpeaker({ ...newSpeaker, biography: e.target.value })}
              disabled={disabled || isSaving}
              rows={3}
              className={styles.formInput}
              style={{ overflow: 'auto', wordBreak: 'break-word', overflowWrap: 'break-word' }}
            />
            <small className={styles.helpText}>
              Brief speaker biography (minimum 50 characters recommended)
            </small>
          </div>

          <label
            htmlFor="new-speaker-use-gravatar"
            style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem', fontSize: '0.9rem' }}
          >
            <input
              id="new-speaker-use-gravatar"
              type="checkbox"
              checked={newSpeaker.use_gravatar || false}
              onChange={(e) => setNewSpeaker({ ...newSpeaker, use_gravatar: e.target.checked })}
              disabled={disabled || isSaving}
            />
            Use Gravatar for profile picture
          </label>

          <button
            type="button"
            onClick={handleAddSpeaker}
            disabled={disabled || isSaving}
            style={{
              padding: '0.75rem 1.5rem',
              backgroundColor: disabled || isSaving ? '#9e9e9e' : '#4caf50',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: disabled || isSaving ? 'not-allowed' : 'pointer',
              fontSize: '0.9rem',
              fontWeight: 'bold',
              opacity: disabled || isSaving ? 0.7 : 1,
            }}
          >
            {isSaving ? 'Adding...' : '+ Add Speaker'}
          </button>
        </div>
      )}
    </div>
  )
}
