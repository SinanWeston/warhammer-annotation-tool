/**
 * Top-of-page progress card: title, overall annotation progress bar,
 * "prioritize by confidence" toggle, confidence badge for the current
 * image (when prioritize is on), refresh-progress button, and the
 * "Start Annotating" button shown only when no image is loaded.
 *
 * Extracted from AnnotationInterface.tsx as part of the Big Refactor
 * (May 2026). Stateless — every piece of state is owned by the parent.
 */

import type { AnnotationProgress } from '../../types'

interface Props {
  progress: AnnotationProgress | null
  prioritize: boolean
  setPrioritize: (v: boolean) => void
  confidenceScore: number | null
  fetchingProgress: boolean
  fetchProgress: () => void
  hasCurrentImage: boolean
  loading: boolean
  onStartAnnotating: () => void
}

export default function HeaderProgressCard({
  progress,
  prioritize,
  setPrioritize,
  confidenceScore,
  fetchingProgress,
  fetchProgress,
  hasCurrentImage,
  loading,
  onStartAnnotating,
}: Props) {
  return (
    <div style={{
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      marginBottom: '2rem',
      padding: '1.5rem',
      backgroundColor: '#1a1a1a',
      borderRadius: '12px',
      border: '1px solid #333',
    }}>
      <div style={{ flex: 1 }}>
        <h1 style={{ margin: 0, fontSize: '2rem', color: '#fff' }}>
          🎨 Training Data Annotation
        </h1>
        {progress && (
          <>
            <div style={{ marginTop: '1rem', fontSize: '1.2rem', color: '#fff', fontWeight: 'bold' }}>
              <span style={{ color: '#10b981', fontSize: '2rem' }}>{progress.annotatedImages.toLocaleString()}</span>
              <span style={{ color: '#666', margin: '0 0.5rem' }}>/</span>
              <span style={{ color: '#aaa' }}>{progress.totalImages.toLocaleString()}</span>
              <span style={{ color: '#666', marginLeft: '1rem', fontSize: '1rem' }}>
                ({progress.percentComplete.toFixed(3)}% complete)
              </span>
            </div>
            <div style={{ marginTop: '0.75rem', height: '8px', backgroundColor: '#333', borderRadius: '4px', overflow: 'hidden' }}>
              <div style={{
                height: '100%',
                width: `${progress.percentComplete}%`,
                backgroundColor: '#10b981',
                transition: 'width 0.5s ease',
                boxShadow: '0 0 10px rgba(16, 185, 129, 0.5)',
              }} />
            </div>
          </>
        )}
      </div>

      <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
        <label style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
          cursor: 'pointer',
          padding: '0.5rem 1rem',
          backgroundColor: prioritize ? '#7c3aed30' : '#1a1a1a',
          border: prioritize ? '1px solid #7c3aed' : '1px solid #333',
          borderRadius: '8px',
          fontSize: '0.85rem',
          color: prioritize ? '#a78bfa' : '#888',
          transition: 'all 0.2s',
        }}>
          <input
            type="checkbox"
            checked={prioritize}
            onChange={e => setPrioritize(e.target.checked)}
            style={{ accentColor: '#7c3aed' }}
          />
          Prioritize by confidence
        </label>

        {confidenceScore !== null && prioritize && (
          <span style={{
            padding: '0.4rem 0.8rem',
            backgroundColor: confidenceScore < 0.3 ? '#dc262640' : confidenceScore < 0.6 ? '#f59e0b40' : '#05966940',
            color: confidenceScore < 0.3 ? '#fca5a5' : confidenceScore < 0.6 ? '#fcd34d' : '#6ee7b7',
            borderRadius: '6px',
            fontSize: '0.8rem',
            fontWeight: 'bold',
          }}>
            Conf: {(confidenceScore * 100).toFixed(0)}%
          </span>
        )}

        <button
          onClick={fetchProgress}
          disabled={fetchingProgress}
          style={{
            padding: '0.75rem 1.5rem',
            backgroundColor: '#374151',
            color: '#fff',
            border: '1px solid #4b5563',
            borderRadius: '8px',
            fontSize: '0.9rem',
            cursor: fetchingProgress ? 'not-allowed' : 'pointer',
            opacity: fetchingProgress ? 0.5 : 1,
            transition: 'all 0.2s',
          }}
          onMouseEnter={(e) => {
            if (!fetchingProgress) e.currentTarget.style.backgroundColor = '#4b5563'
          }}
          onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = '#374151' }}
        >
          {fetchingProgress ? '⏳ Updating...' : '🔄 Refresh Progress'}
        </button>

        {!hasCurrentImage && (
          <button
            onClick={onStartAnnotating}
            disabled={loading}
            style={{
              padding: '1rem 2rem',
              backgroundColor: '#2563eb',
              color: '#fff',
              border: 'none',
              borderRadius: '8px',
              fontSize: '1rem',
              fontWeight: 'bold',
              cursor: loading ? 'not-allowed' : 'pointer',
              opacity: loading ? 0.5 : 1,
            }}
          >
            {loading ? 'Loading...' : 'Start Annotating'}
          </button>
        )}
      </div>
    </div>
  )
}
