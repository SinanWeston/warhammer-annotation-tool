/**
 * AI prediction validation panel — the per-prediction accept/redraw/reject
 * list shown above the canvas when predictions arrive (DINO proposals
 * or YOLO inference). Three terminal actions per row, plus three bulk
 * actions in the header (Accept High Conf / Accept All / Reject All).
 *
 * Hover/click syncs `highlightedId` upward so the canvas can outline the
 * focused box. Keyboard navigation (Tab/A/W/R/Enter) is still owned by
 * the parent — this component is presentational.
 *
 * Extracted from AnnotationInterface.tsx as part of the Big Refactor.
 */

import type { BboxAnnotation } from '../../types'

interface Props {
  predictions: BboxAnnotation[]
  highlightedId: string | null
  setHighlightedId: (id: string | null) => void
  onAccept: (id: string) => void
  onReject: (id: string) => void
  onRedraw: (id: string) => void
  onAcceptAll: () => void
  onRejectAll: () => void
  onAcceptHighConf: () => void
}

export default function PredictionValidationPanel({
  predictions,
  highlightedId,
  setHighlightedId,
  onAccept,
  onReject,
  onRedraw,
  onAcceptAll,
  onRejectAll,
  onAcceptHighConf,
}: Props) {
  if (predictions.length === 0) return null

  return (
    <div style={{
      padding: '1.5rem',
      backgroundColor: '#1e293b',
      borderRadius: '8px',
      border: '2px solid #3b82f6',
      marginBottom: '1rem',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
        <h3 style={{ margin: 0, color: '#fff' }}>🤖 AI Predictions - Validate Each Box</h3>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button
            onClick={onAcceptHighConf}
            style={{
              padding: '0.4rem 0.75rem',
              backgroundColor: '#0d9488',
              color: '#fff',
              border: 'none',
              borderRadius: '6px',
              fontSize: '0.8rem',
              cursor: 'pointer',
            }}
            title="Accept predictions with >80% confidence"
          >
            ✓ Accept High Conf
          </button>
          <button
            onClick={onAcceptAll}
            style={{
              padding: '0.4rem 0.75rem',
              backgroundColor: '#059669',
              color: '#fff',
              border: 'none',
              borderRadius: '6px',
              fontSize: '0.8rem',
              cursor: 'pointer',
              fontWeight: 'bold',
            }}
            title="Accept all remaining predictions and save (Enter)"
          >
            ✓ Accept All
          </button>
          <button
            onClick={onRejectAll}
            style={{
              padding: '0.4rem 0.75rem',
              backgroundColor: '#dc2626',
              color: '#fff',
              border: 'none',
              borderRadius: '6px',
              fontSize: '0.8rem',
              cursor: 'pointer',
            }}
            title="Reject all remaining predictions"
          >
            ✗ Reject All
          </button>
        </div>
      </div>

      <div style={{
        display: 'flex',
        gap: '1rem',
        marginBottom: '0.75rem',
        padding: '0.5rem 0.75rem',
        backgroundColor: '#0f172a',
        borderRadius: '4px',
        fontSize: '0.75rem',
        color: '#64748b',
        flexWrap: 'wrap',
      }}>
        <span><kbd style={{ color: '#94a3b8', backgroundColor: '#1e293b', padding: '1px 5px', borderRadius: '3px', border: '1px solid #334155' }}>Tab</kbd> cycle</span>
        <span><kbd style={{ color: '#94a3b8', backgroundColor: '#1e293b', padding: '1px 5px', borderRadius: '3px', border: '1px solid #334155' }}>A</kbd> accept</span>
        <span><kbd style={{ color: '#94a3b8', backgroundColor: '#1e293b', padding: '1px 5px', borderRadius: '3px', border: '1px solid #334155' }}>W</kbd> wrong</span>
        <span><kbd style={{ color: '#94a3b8', backgroundColor: '#1e293b', padding: '1px 5px', borderRadius: '3px', border: '1px solid #334155' }}>R</kbd> redraw</span>
        <span><kbd style={{ color: '#94a3b8', backgroundColor: '#1e293b', padding: '1px 5px', borderRadius: '3px', border: '1px solid #334155' }}>Enter</kbd> accept all + save</span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        {predictions.map((pred, idx) => {
          const isHighlighted = pred.id === highlightedId
          return (
            <div
              key={pred.id}
              onMouseEnter={() => setHighlightedId(pred.id)}
              onMouseLeave={() => setHighlightedId(null)}
              onClick={() => setHighlightedId(pred.id)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '1rem',
                padding: '0.75rem 1rem',
                backgroundColor: isHighlighted ? '#1e3a5f' : '#0f172a',
                borderRadius: '6px',
                border: isHighlighted ? '2px solid #00ffff' : '1px solid #334155',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
            >
              <span style={{
                color: isHighlighted ? '#00ffff' : '#94a3b8',
                fontWeight: 'bold',
                minWidth: '30px',
                fontSize: '1.1rem',
              }}>
                #{idx + 1}
              </span>
              <span style={{ color: '#fff', flex: 1 }}>
                {pred.classLabel.replace(/_/g, ' ')}
                <span style={{ color: '#64748b', marginLeft: '0.5rem' }}>
                  ({((pred.confidence || 0) * 100).toFixed(0)}% conf)
                </span>
              </span>

              <button
                onClick={(e) => { e.stopPropagation(); onAccept(pred.id) }}
                style={{
                  padding: '0.5rem 1rem',
                  backgroundColor: '#059669',
                  color: '#fff',
                  border: 'none',
                  borderRadius: '6px',
                  fontSize: '1rem',
                  cursor: 'pointer',
                  fontWeight: 'bold',
                }}
                title="Correct - Accept this box"
              >
                ✓ Correct
              </button>

              <button
                onClick={(e) => { e.stopPropagation(); onRedraw(pred.id) }}
                style={{
                  padding: '0.5rem 1rem',
                  backgroundColor: '#eab308',
                  color: '#000',
                  border: 'none',
                  borderRadius: '6px',
                  fontSize: '1rem',
                  cursor: 'pointer',
                  fontWeight: 'bold',
                }}
                title="Redraw - Delete and draw manually"
              >
                ✎ Redraw
              </button>

              <button
                onClick={(e) => { e.stopPropagation(); onReject(pred.id) }}
                style={{
                  padding: '0.5rem 1rem',
                  backgroundColor: '#dc2626',
                  color: '#fff',
                  border: 'none',
                  borderRadius: '6px',
                  fontSize: '1rem',
                  cursor: 'pointer',
                  fontWeight: 'bold',
                }}
                title="Wrong - Remove this box"
              >
                ✗ Wrong
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
