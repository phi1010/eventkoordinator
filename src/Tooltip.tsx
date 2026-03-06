import { useState, useRef, useLayoutEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import styles from './Tooltip.module.css'

interface TooltipProps {
  content?: string
  children: React.ReactNode
  maxWidth?: string
  enabled?: boolean  // Only show tooltip when enabled is true
}

export function Tooltip({ content, children, maxWidth = '400px', enabled = true }: TooltipProps) {
  const [isVisible, setIsVisible] = useState(false)
  const triggerRef = useRef<HTMLDivElement>(null)
  const tooltipRef = useRef<HTMLDivElement>(null)

  // Only show tooltip if enabled and content exists
  const shouldShowTooltip = enabled && content

  useLayoutEffect(() => {
    if (isVisible && shouldShowTooltip && triggerRef.current && tooltipRef.current) {
      const triggerRect = triggerRef.current.getBoundingClientRect()
      const tooltipRect = tooltipRef.current.getBoundingClientRect()

      // Position tooltip to the right of the trigger
      let left = triggerRect.right + 10
      let top = triggerRect.top

      // If tooltip would overflow right edge, show on left instead
      if (left + tooltipRect.width > window.innerWidth) {
        left = triggerRect.left - tooltipRect.width - 10
      }

      // If tooltip would overflow bottom, adjust top
      if (top + tooltipRect.height > window.innerHeight) {
        top = window.innerHeight - tooltipRect.height - 10
      }

      // If tooltip would overflow top, adjust
      if (top < 10) {
        top = 10
      }

      // Apply position directly to avoid setState warning
      tooltipRef.current.style.top = `${top}px`
      tooltipRef.current.style.left = `${left}px`
    }
  }, [isVisible, shouldShowTooltip])

  return (
    <div
      ref={triggerRef}
      className={styles.tooltipTrigger}
      onMouseEnter={() => setIsVisible(true)}
      onMouseLeave={() => setIsVisible(false)}
      onFocus={() => setIsVisible(true)}
      onBlur={() => setIsVisible(false)}
      tabIndex={0}
      role="button"
      aria-describedby={isVisible ? 'tooltip-content' : undefined}
    >
      {children}

      {isVisible && shouldShowTooltip && (
        <div
          ref={tooltipRef}
          id="tooltip-content"
          role="tooltip"
          className={styles.tooltip}
          style={{
            maxWidth,
          }}
        >
          <div className={styles.tooltipContent}>
            <ReactMarkdown>{content}</ReactMarkdown>
          </div>
        </div>
      )}
    </div>
  )
}


