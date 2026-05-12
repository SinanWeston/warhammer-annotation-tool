/**
 * Per-faction progress card grid. Click a card to filter the queue to
 * that faction. Each card shows annotated/total, a progress bar, and
 * pending/legacy pills (only when non-zero, so completed factions
 * stay visually clean).
 */

import type { AnnotationProgress } from '../../types'

interface Props {
  progress: AnnotationProgress | null
  selectedFaction: string | null
  onFactionToggle: (faction: string | null) => void
}

export default function FactionProgressGrid({ progress, selectedFaction, onFactionToggle }: Props) {
  if (!progress) return null

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
      gap: '1rem',
      marginBottom: '2rem',
    }}>
      {Object.entries(progress.byFaction)
        .sort((a, b) => b[1].total - a[1].total)
        .map(([faction, stats]) => {
          const isSelected = selectedFaction === faction
          const isComplete = stats.annotated >= stats.total
          return (
            <div
              key={faction}
              onClick={() => onFactionToggle(isSelected ? null : faction)}
              style={{
                padding: '1rem',
                backgroundColor: isSelected ? '#1a2a1a' : '#1a1a1a',
                borderRadius: '8px',
                border: isSelected ? '2px solid #10b981' : '1px solid #333',
                cursor: 'pointer',
                transition: 'all 0.2s',
                opacity: isComplete && !isSelected ? 0.6 : 1,
              }}
            >
              <div style={{
                color: isSelected ? '#10b981' : '#aaa',
                fontSize: '0.8rem',
                marginBottom: '0.5rem',
                textTransform: 'capitalize',
                fontWeight: isSelected ? 'bold' : 'normal',
              }}>
                {faction.replace(/_/g, ' ')}
                {isSelected && ' ●'}
              </div>
              <div style={{ color: '#fff', fontSize: '1.2rem', fontWeight: 'bold' }}>
                {stats.annotated} / {stats.total}
              </div>
              <div style={{ marginTop: '0.5rem', height: '4px', backgroundColor: '#333', borderRadius: '2px', overflow: 'hidden' }}>
                <div style={{
                  height: '100%',
                  width: `${(stats.annotated / stats.total) * 100}%`,
                  backgroundColor: isComplete ? '#059669' : '#10b981',
                  transition: 'width 0.3s',
                }} />
              </div>
              {(stats.pending > 0 || stats.legacy > 0) && (
                <div style={{
                  marginTop: '0.5rem',
                  display: 'flex',
                  gap: '0.35rem',
                  fontSize: '0.7rem',
                }}>
                  {stats.pending > 0 && (
                    <span
                      title={`${stats.pending} image(s) have bboxes missing unit_slug — pick Status: Pending to revisit`}
                      style={{
                        padding: '0.1rem 0.4rem',
                        borderRadius: '3px',
                        backgroundColor: '#3b1f5a',
                        color: '#c4a0ff',
                      }}
                    >
                      {stats.pending} pending
                    </span>
                  )}
                  {stats.legacy > 0 && (
                    <span
                      title={`${stats.legacy} annotation(s) from before unit_slug existed. Pick Status: Legacy to backfill.`}
                      style={{
                        padding: '0.1rem 0.4rem',
                        borderRadius: '3px',
                        backgroundColor: '#3a3a3a',
                        color: '#999',
                      }}
                    >
                      {stats.legacy} legacy
                    </span>
                  )}
                </div>
              )}
            </div>
          )
        })}
    </div>
  )
}
