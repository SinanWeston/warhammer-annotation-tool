/**
 * Status filter row. UI surface is 3 primary pills + a "Browse ▾"
 * dropdown for the read-only queues. Backend supports 7 values
 * (unannotated | pending | legacy | pseudo | flagged | frozen_eval | all)
 * — the UI just doesn't expose them with equal weight, because 80%+
 * of sessions sit on `unannotated`.
 *
 *   Primary:  [Unannotated]  [Pending (N)]  [Pseudo-labelled]
 *   Browse ▾: Legacy / Flagged / Frozen eval (200) / All
 *
 * "Pseudo-labelled" hides until Phase F1 actually writes some (i.e.,
 * progress.pseudoImages > 0). "Legacy" hides if zero.
 *
 * Power-user shortcuts: 1/2/3/4 jump to the primary pills + Browse menu
 * (handled in AnnotationInterface's keyboard router).
 *
 * NB: parent's onStatusChange currently fires loadNextImage BEFORE
 * setSelectedStatus settles, so the first /next after a pill click goes
 * out with the stale status. Commit 10 (useReducer + reload-via-effect)
 * fixes that.
 */

import { useEffect, useRef, useState } from 'react'
import type { AnnotationProgress } from '../../types'

export type AnnotatorStatus =
  | 'unannotated'
  | 'pending'
  | 'legacy'
  | 'pseudo'
  | 'flagged'
  | 'frozen_eval'
  | 'all'

interface Props {
  selectedStatus: AnnotatorStatus
  onStatusChange: (next: AnnotatorStatus) => void
  progress: AnnotationProgress | null
}

interface Option {
  key: AnnotatorStatus
  label: string
  tooltip: string
}

export default function StatusFilterRow({ selectedStatus, onStatusChange, progress }: Props) {
  const [browseOpen, setBrowseOpen] = useState(false)
  const browseMenuRef = useRef<HTMLDivElement | null>(null)

  // Close the Browse dropdown on outside click.
  useEffect(() => {
    if (!browseOpen) return
    const handler = (e: MouseEvent) => {
      if (browseMenuRef.current && !browseMenuRef.current.contains(e.target as Node)) {
        setBrowseOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [browseOpen])

  const primary: Option[] = [
    {
      key: 'unannotated',
      label: 'Unannotated',
      tooltip: 'Fresh images you haven\'t saved an annotation for yet (default).',
    },
    {
      key: 'pending',
      label: `Pending${progress?.pendingImages ? ` (${progress.pendingImages})` : ''}`,
      tooltip: 'Annotated images where at least one bbox is missing unit_slug — come back to fill them in.',
    },
  ]

  // Pseudo-labelled only surfaces when Phase F1 has actually written
  // some. Until then the pill would just confuse — there's nothing to click.
  // pseudoImages is optional on AnnotationProgress (older snapshots don't carry it).
  const pseudoCount = (progress as (AnnotationProgress & { pseudoImages?: number }) | null)?.pseudoImages ?? 0
  if (pseudoCount > 0) {
    primary.push({
      key: 'pseudo',
      label: `Pseudo-labelled (${pseudoCount})`,
      tooltip: 'Phase F1 auto-labels awaiting box review. Correct any wrong boxes, then save — that promotes the image out of this queue.',
    })
  }

  const browse: Option[] = [
    {
      key: 'legacy',
      label: `Legacy${progress?.legacyImages ? ` (${progress.legacyImages})` : ''}`,
      tooltip: 'Grandfathered annotations from before unit_slug existed. Backfill candidates.',
    },
    {
      key: 'flagged',
      label: 'Flagged',
      tooltip: 'Images you marked unusable via X. Browse-only — re-confirm or un-flag.',
    },
    {
      key: 'frozen_eval',
      label: 'Frozen eval (200)',
      tooltip: 'Phase C held-out scene benchmark. Browse-only — do not retrain on these.',
    },
    {
      key: 'all',
      label: 'All',
      tooltip: 'Every image, in priority order: pending > legacy > unannotated. Flagged excluded.',
    },
  ]

  const browseActive = browse.some(o => o.key === selectedStatus)
  const activeBrowseLabel = browse.find(o => o.key === selectedStatus)?.label ?? null

  const pillStyle = (active: boolean): React.CSSProperties => ({
    padding: '0.4rem 0.9rem',
    backgroundColor: active ? '#a855f7' : '#2a2a2a',
    color: '#fff',
    border: '1px solid ' + (active ? '#a855f7' : '#444'),
    borderRadius: '4px',
    cursor: 'pointer',
    fontSize: '0.9rem',
  })

  return (
    <div style={{
      marginBottom: '0.5rem',
      padding: '0.75rem 1rem',
      backgroundColor: '#1a1a1a',
      borderRadius: '8px',
      border: '1px solid #333',
      display: 'flex',
      alignItems: 'center',
      gap: '0.75rem',
      flexWrap: 'wrap',
      position: 'relative',
    }}>
      <span style={{ color: '#aaa', fontSize: '0.9rem' }}>Status:</span>
      {primary.map(opt => (
        <button
          key={opt.key}
          onClick={() => { if (selectedStatus !== opt.key) onStatusChange(opt.key) }}
          style={pillStyle(selectedStatus === opt.key)}
          title={opt.tooltip}
        >
          {opt.label}
        </button>
      ))}

      <div ref={browseMenuRef} style={{ position: 'relative' }}>
        <button
          onClick={() => setBrowseOpen(o => !o)}
          style={{
            ...pillStyle(browseActive),
            display: 'flex',
            alignItems: 'center',
            gap: '0.3rem',
          }}
          title="Browse legacy, flagged, frozen-eval, and the all-images view."
        >
          {browseActive && activeBrowseLabel ? activeBrowseLabel : 'Browse'}
          <span style={{ fontSize: '0.7rem', opacity: 0.8 }}>▾</span>
        </button>
        {browseOpen && (
          <div style={{
            position: 'absolute',
            top: 'calc(100% + 4px)',
            left: 0,
            minWidth: '260px',
            padding: '0.4rem',
            backgroundColor: '#1a1a1a',
            border: '1px solid #444',
            borderRadius: '6px',
            display: 'flex',
            flexDirection: 'column',
            gap: '0.25rem',
            zIndex: 10,
            boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
          }}>
            {browse.map(opt => {
              const active = selectedStatus === opt.key
              return (
                <button
                  key={opt.key}
                  onClick={() => {
                    setBrowseOpen(false)
                    if (selectedStatus !== opt.key) onStatusChange(opt.key)
                  }}
                  style={{
                    ...pillStyle(active),
                    textAlign: 'left',
                  }}
                  title={opt.tooltip}
                >
                  {opt.label}
                </button>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
