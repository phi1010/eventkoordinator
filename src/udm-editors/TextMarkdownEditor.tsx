import { useEffect, useRef } from 'react'
import { StacksEditor, EditorType } from '@stackoverflow/stacks-editor'
import '@stackoverflow/stacks-editor/dist/styles.css'
import '../stacks-scoped.css'
import type { FieldInputProps } from './types'
import { fieldEditorRegistry } from './registry'
import styles from '../UdmEntityEditor.module.css'

function TextMarkdownEditor({ value, onChange, disabled }: FieldInputProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const editorRef = useRef<StacksEditor | null>(null)
  const onChangeRef = useRef(onChange)
  const isSettingContentRef = useRef(false)

  useEffect(() => { onChangeRef.current = onChange })

  useEffect(() => {
    if (!containerRef.current) return
    containerRef.current.innerHTML = ''
    const editor = new StacksEditor(
      containerRef.current,
      (value as string) ?? '',
      { defaultView: EditorType.Commonmark, imageUpload: { handler: undefined } },
    )
    editorRef.current = editor

    function patchDispatch() {
      const view = editor.editorView
      const orig = view.dispatch.bind(view)
      view.dispatch = (tr) => {
        orig(tr)
        if (!isSettingContentRef.current && tr.docChanged) {
          onChangeRef.current(editor.content)
        }
      }
    }
    patchDispatch()

    const target = containerRef.current
    function handleViewChange() { patchDispatch() }
    target.addEventListener('change', handleViewChange)

    if (disabled) editor.disable()

    return () => {
      target.removeEventListener('change', handleViewChange)
      editor.destroy()
      editorRef.current = null
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const editor = editorRef.current
    if (!editor) return
    const incoming = (value as string) ?? ''
    if (incoming !== editor.content) {
      isSettingContentRef.current = true
      editor.content = incoming
      isSettingContentRef.current = false
    }
  }, [value])

  useEffect(() => {
    const editor = editorRef.current
    if (!editor) return
    if (disabled) editor.disable()
    else editor.enable()
  }, [disabled])

  const len = ((value as string) ?? '').length
  return (
    <div>
      <div ref={containerRef} className={styles.markdownEditor} />
      <div className={styles.lenHint}>{len}</div>
    </div>
  )
}

fieldEditorRegistry.register('text_markdown', TextMarkdownEditor)
