import { useState, useEffect, useRef, useCallback } from 'react'

export interface TourStep {
  target: string
  title: string
  body: string
}

interface TourProps {
  steps: TourStep[]
  onClose: () => void
}

const PAD = 10

export default function Tour({ steps, onClose }: TourProps) {
  const [step, setStep] = useState(0)
  const [spotlight, setSpotlight] = useState<DOMRect | null>(null)
  const popRef = useRef<HTMLDivElement>(null)
  const current = steps[step]

  const refreshSpotlight = useCallback(() => {
    if (!current) return
    const el = document.querySelector(`[data-tour="${current.target}"]`)
    setSpotlight(el ? el.getBoundingClientRect() : null)
  }, [current])

  useEffect(() => {
    const id = setTimeout(refreshSpotlight, 30)
    window.addEventListener('resize', refreshSpotlight)
    window.addEventListener('scroll', refreshSpotlight, { passive: true })
    return () => {
      clearTimeout(id)
      window.removeEventListener('resize', refreshSpotlight)
      window.removeEventListener('scroll', refreshSpotlight)
    }
  }, [refreshSpotlight])

  useEffect(() => {
    popRef.current?.querySelector<HTMLElement>('button')?.focus()
  }, [step])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { onClose(); return }
      if (e.key === 'ArrowRight') { setStep(s => Math.min(steps.length - 1, s + 1)); return }
      if (e.key === 'ArrowLeft') { setStep(s => Math.max(0, s - 1)); return }
      if (e.key === 'Tab') {
        const pop = popRef.current
        if (!pop) return
        const els = Array.from(pop.querySelectorAll<HTMLElement>('button,[tabindex="0"]'))
        if (!els.length) return
        e.preventDefault()
        const idx = els.indexOf(document.activeElement as HTMLElement)
        els[(idx + (e.shiftKey ? -1 : 1) + els.length) % els.length]?.focus()
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [steps.length, onClose])

  if (!current) return null

  const vw = window.innerWidth
  const vh = window.innerHeight
  const popW = Math.min(300, vw - 32)

  let popLeft = Math.round(vw / 2 - popW / 2)
  let popTop  = Math.round(vh / 2 - 90)

  if (spotlight) {
    popLeft = Math.max(16, Math.min(
      Math.round(spotlight.left + spotlight.width / 2 - popW / 2),
      vw - popW - 16,
    ))
    const below = spotlight.bottom + PAD + 12
    const above = spotlight.top - PAD - 12 - 190
    popTop = below + 190 < vh ? below : Math.max(16, above)
  }

  const next = () => { if (step < steps.length - 1) setStep(s => s + 1); else onClose() }
  const prev = () => setStep(s => Math.max(0, s - 1))

  return (
    <>
      <div className="tour-click-catcher" onClick={onClose} aria-hidden="true"/>
      {spotlight && (
        <div
          className="tour-spotlight"
          style={{
            left: spotlight.left - PAD,
            top: spotlight.top - PAD,
            width: spotlight.width + PAD * 2,
            height: spotlight.height + PAD * 2,
          }}
          aria-hidden="true"
        />
      )}
      <div
        ref={popRef}
        className="tour-popover"
        style={{ left: popLeft, top: popTop, width: popW }}
        role="dialog"
        aria-modal="true"
        aria-label={`Guided tour step ${step + 1} of ${steps.length}`}
      >
        <div className="tour-popover-head">
          <span className="tour-step-label" aria-hidden="true">{step + 1} / {steps.length}</span>
          <button className="btn tour-close-btn" onClick={onClose} aria-label="Close guided tour">✕</button>
        </div>
        <p className="tour-popover-title">{current.title}</p>
        <p className="tour-popover-body">{current.body}</p>
        <div className="tour-dots" aria-hidden="true">
          {steps.map((_, i) => (
            <span key={i} className={`tour-dot${i === step ? ' active' : ''}`}/>
          ))}
        </div>
        <div className="tour-popover-nav">
          {step > 0 && (
            <button className="btn tour-back-btn" onClick={prev}>Back</button>
          )}
          <button className="btn btn-primary tour-next-btn" onClick={next}>
            {step < steps.length - 1 ? 'Next' : 'Done'}
          </button>
        </div>
        {step < steps.length - 1 && (
          <button className="tour-skip-btn" onClick={onClose}>Skip tour</button>
        )}
      </div>
    </>
  )
}
