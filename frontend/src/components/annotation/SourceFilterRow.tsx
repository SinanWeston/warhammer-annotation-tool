/**
 * Source filter pill row. Drives `selectedSource` which feeds `?source=`
 * on /api/annotate/next. `null` = all sources. Sources are sourced from
 * the taxonomy endpoint's `sources` field (ANNOTATION_SOURCES env on
 * backend). Hidden when only one source is configured.
 */

import type { Taxonomy } from '../../types'

interface Props {
  selectedSource: string | null
  onSourceChange: (next: string | null) => void
  taxonomy: Taxonomy | null
}

export default function SourceFilterRow({ selectedSource, onSourceChange, taxonomy }: Props) {
  if (!taxonomy?.sources || taxonomy.sources.length <= 1) return null

  return (
    <div style={{
      marginBottom: '1.5rem',
      padding: '0.75rem 1rem',
      backgroundColor: '#1a1a1a',
      borderRadius: '8px',
      border: '1px solid #333',
      display: 'flex',
      alignItems: 'center',
      gap: '0.75rem',
      flexWrap: 'wrap',
    }}>
      <span style={{ color: '#aaa', fontSize: '0.9rem' }}>Source:</span>
      <button
        onClick={() => {
          if (selectedSource !== null) onSourceChange(null)
        }}
        style={{
          padding: '0.4rem 0.9rem',
          backgroundColor: selectedSource === null ? '#10b981' : '#2a2a2a',
          color: '#fff',
          border: '1px solid ' + (selectedSource === null ? '#10b981' : '#444'),
          borderRadius: '4px',
          cursor: 'pointer',
          fontSize: '0.9rem',
          textTransform: 'capitalize',
        }}
        title="Show images from every configured source"
      >
        all
      </button>
      {taxonomy.sources.map(src => {
        const active = selectedSource === src
        return (
          <button
            key={src}
            onClick={() => onSourceChange(src)}
            style={{
              padding: '0.4rem 0.9rem',
              backgroundColor: active ? '#10b981' : '#2a2a2a',
              color: '#fff',
              border: '1px solid ' + (active ? '#10b981' : '#444'),
              borderRadius: '4px',
              cursor: 'pointer',
              fontSize: '0.9rem',
              textTransform: 'capitalize',
            }}
            title={`Only show images whose source folder is "${src}/"`}
          >
            {src}
          </button>
        )
      })}
    </div>
  )
}
