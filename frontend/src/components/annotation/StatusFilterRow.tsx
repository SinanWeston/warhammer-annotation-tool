/**
 * Status filter pill row. Drives `selectedStatus` which feeds the
 * `?status=` param on /api/annotate/next.
 *
 * Currently 6 pills (7 if you count "All"). Commit 8 will collapse this
 * UI to 4 (Unannotated | Pending | Pseudo | Browse ▾) while the backend
 * keeps all 7 status values. Extracting first to keep the diff readable.
 *
 * NB: the inline onClick has a known closure bug — it fires
 * `onStatusChange` (which calls `loadNextImage`) BEFORE `setSelectedStatus`
 * settles, so the first /next after a pill click goes out with the stale
 * status. Commit 10 (useReducer + reload-via-effect) fixes that.
 */

import type { AnnotationProgress } from '../../types'

export type AnnotatorStatus =
  | 'unannotated'
  | 'pending'
  | 'legacy'
  | 'pseudo'
  | 'frozen_eval'
  | 'all'

interface Props {
  selectedStatus: AnnotatorStatus
  onStatusChange: (next: AnnotatorStatus) => void
  progress: AnnotationProgress | null
}

export default function StatusFilterRow({ selectedStatus, onStatusChange, progress }: Props) {
  const options: Array<readonly [AnnotatorStatus, string, string]> = [
    ['unannotated', 'Unannotated', 'Show fresh images you haven\'t saved an annotation for yet'],
    ['pending',     `Pending${progress?.pendingImages ? ` (${progress.pendingImages})` : ''}`, 'Show annotated images where at least one bbox is missing its unit_slug — return here to fill them in'],
    ['legacy',      `Legacy${progress?.legacyImages ? ` (${progress.legacyImages})` : ''}`, 'Grandfathered annotations from before unit_slug existed. Pick here when you want to backfill units on old corpus.'],
    ['pseudo',      'Pseudo-labelled', 'Phase F1 auto-labels awaiting box review. Correct any wrong boxes, then save — that promotes the image out of this queue.'],
    ['frozen_eval', 'Frozen eval (200)', 'Phase C held-out scene benchmark. Browse-only review — do not retrain on these. Manifest: data/scene_benchmark/eval_200.json.'],
    ['all',         'All',         'Show every image (pending > legacy > unannotated)'],
  ]

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
    }}>
      <span style={{ color: '#aaa', fontSize: '0.9rem' }}>Status:</span>
      {options.map(([key, label, tooltip]) => {
        const active = selectedStatus === key
        return (
          <button
            key={key}
            onClick={() => {
              if (selectedStatus !== key) onStatusChange(key)
            }}
            style={{
              padding: '0.4rem 0.9rem',
              backgroundColor: active ? '#a855f7' : '#2a2a2a',
              color: '#fff',
              border: '1px solid ' + (active ? '#a855f7' : '#444'),
              borderRadius: '4px',
              cursor: 'pointer',
              fontSize: '0.9rem',
            }}
            title={tooltip}
          >
            {label}
          </button>
        )
      })}
    </div>
  )
}
