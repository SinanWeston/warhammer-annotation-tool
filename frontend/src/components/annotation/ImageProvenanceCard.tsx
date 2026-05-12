/**
 * Provenance / metadata strip shown above the canvas. Surfaces:
 *  - faction (already-remapped, capitalised) / source / dimensions
 *  - filename (always)
 *  - CMON provenance (title + artist + score + tags + source link),
 *    when the backend's buildImageMeta resolved a manifest.json
 *  - reverse-image-search buttons (Google Lens / Yandex / Bing) that
 *    copy the current frame as PNG to the clipboard and open the engine
 *    in a new tab. Status text shows the copy result for 5s.
 *
 * Internal state: `reverseSearchStatus` — was hoisted to
 * AnnotationInterface but is only consumed here, so it lives with the
 * component now.
 */

import { useState } from 'react'
import type { AnnotatorImage } from '../../types'

// Reverse-image-search engines. All accept a pasted clipboard image on
// their landing/upload page; we can't use their `?image_url=` params
// because the annotator runs on localhost and the engines fetch URLs
// server-side. One-click copy-to-clipboard + new-tab is the next best
// thing — paste with Ctrl+V / Cmd+V once the tab opens.
const REVERSE_IMAGE_ENGINES = [
  { name: 'Google Lens', url: 'https://lens.google.com/' },
  { name: 'Yandex', url: 'https://yandex.com/images/' },
  { name: 'Bing', url: 'https://www.bing.com/visualsearch' },
] as const

// Clipboard API only reliably accepts PNG across browsers, so re-encode
// JPEG source frames via a throwaway canvas.
async function imageDataUrlToPngBlob(dataUrl: string): Promise<Blob> {
  const src = await fetch(dataUrl).then(r => r.blob())
  if (src.type === 'image/png') return src
  const img = new Image()
  const objUrl = URL.createObjectURL(src)
  try {
    await new Promise<void>((resolve, reject) => {
      img.onload = () => resolve()
      img.onerror = () => reject(new Error('decode failed'))
      img.src = objUrl
    })
    const canvas = document.createElement('canvas')
    canvas.width = img.naturalWidth
    canvas.height = img.naturalHeight
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('no 2d context')
    ctx.drawImage(img, 0, 0)
    return await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob(b => b ? resolve(b) : reject(new Error('toBlob failed')), 'image/png')
    )
  } finally {
    URL.revokeObjectURL(objUrl)
  }
}

interface Props {
  image: AnnotatorImage
  /** Already-remapped, display-ready faction (e.g. "space marines"). The
   *  parent owns the FACTION_REMAP table so this component doesn't need
   *  to import it. */
  displayFaction: string
  annotationCount: number
}

export default function ImageProvenanceCard({ image, displayFaction, annotationCount }: Props) {
  const [reverseSearchStatus, setReverseSearchStatus] = useState<string | null>(null)

  return (
    <div style={{
      padding: '1rem',
      backgroundColor: '#1a1a1a',
      borderRadius: '8px',
      border: '1px solid #333',
      marginBottom: '1rem',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem' }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ color: '#aaa', fontSize: '0.8rem' }}>Current Image:</div>
          <div style={{ color: '#fff', fontSize: '1rem', marginTop: '0.25rem' }}>
            <span style={{ color: '#10b981', textTransform: 'capitalize' }}>
              {displayFaction.replace(/_/g, ' ')}
            </span>
            {' '} / {image.source}
            {' '} / {image.width}x{image.height}
          </div>
          {image.meta && (
            <div style={{
              marginTop: '0.5rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '0.15rem',
              fontSize: '0.85rem',
              color: '#bbb',
              minWidth: 0,
            }}>
              <div style={{
                fontFamily: 'monospace',
                color: '#888',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                maxWidth: '60ch',
              }} title={image.meta.filename}>
                {image.meta.filename}
              </div>
              {image.meta.title && (
                <div style={{ color: '#fff' }}>
                  <span style={{ color: '#888', fontSize: '0.75rem', marginRight: '0.4rem' }}>title</span>
                  {image.meta.sourceUrl ? (
                    <a
                      href={image.meta.sourceUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ color: '#a855f7', textDecoration: 'none' }}
                      title="Open source page in a new tab"
                    >
                      {image.meta.title}
                      <span style={{ marginLeft: '0.3rem', fontSize: '0.75rem' }}>↗</span>
                    </a>
                  ) : (
                    image.meta.title
                  )}
                  {image.meta.artist && (
                    <span style={{ color: '#888', marginLeft: '0.5rem', fontSize: '0.85rem' }}>
                      by {image.meta.artist}
                    </span>
                  )}
                  {/* Community score (0–10). Prefix with vote count in
                      a muted tone so low-sample-size scores read
                      sceptically. High-score images are usually cleaner
                      reference shots. */}
                  {typeof image.meta.score === 'number' && (
                    <span style={{
                      marginLeft: '0.6rem',
                      fontSize: '0.8rem',
                      color: image.meta.score >= 7 ? '#fbbf24' : '#888',
                    }} title={`CMON community score (${image.meta.votes ?? '?'} votes)`}>
                      ★ {image.meta.score.toFixed(1)}
                      {image.meta.votes != null && (
                        <span style={{ color: '#666', marginLeft: '0.25rem', fontSize: '0.75rem' }}>
                          ({image.meta.votes})
                        </span>
                      )}
                    </span>
                  )}
                </div>
              )}
              {image.meta.tags && image.meta.tags.length > 0 && (
                <div style={{
                  marginTop: '0.2rem',
                  display: 'flex',
                  gap: '0.3rem',
                  flexWrap: 'wrap',
                }}>
                  {image.meta.tags.slice(0, 10).map(t => (
                    <span key={t} style={{
                      padding: '0.05rem 0.35rem',
                      backgroundColor: '#2a2a2a',
                      borderRadius: '3px',
                      color: '#888',
                      fontSize: '0.7rem',
                    }}>{t}</span>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', flexShrink: 0, alignItems: 'center', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          <div style={{ display: 'flex', gap: '0.3rem', alignItems: 'center' }}>
            <span style={{ color: '#888', fontSize: '0.75rem', marginRight: '0.15rem' }}>Reverse search:</span>
            {REVERSE_IMAGE_ENGINES.map(engine => (
              <button
                key={engine.name}
                type="button"
                disabled={!image.imageBase64}
                title={`Open ${engine.name} in a new tab and copy the current scene to the clipboard. Paste with Ctrl+V (or Cmd+V) on the engine page.`}
                onClick={() => {
                  const dataUrl = image.imageBase64
                  if (!dataUrl) return
                  // Must submit the clipboard write *before* window.open, otherwise
                  // the new tab steals focus and Chrome rejects writes on unfocused
                  // documents. ClipboardItem accepts a Promise<Blob>, so the browser
                  // holds the user gesture while the PNG encoding resolves.
                  const writePromise = navigator.clipboard.write([
                    new ClipboardItem({ 'image/png': imageDataUrlToPngBlob(dataUrl) }),
                  ])
                  window.open(engine.url, '_blank', 'noopener,noreferrer')
                  setReverseSearchStatus(`Copying for ${engine.name}…`)
                  writePromise
                    .then(() => setReverseSearchStatus(`Copied — paste in ${engine.name} tab (Ctrl+V)`))
                    .catch(err => {
                      console.error('Reverse image clipboard copy failed:', err)
                      setReverseSearchStatus(`Copy failed (${err?.name || 'error'}) — save the image manually and upload to ${engine.name}`)
                    })
                  window.setTimeout(() => setReverseSearchStatus(null), 5000)
                }}
                style={{
                  padding: '0.35rem 0.65rem',
                  backgroundColor: '#2a2a2a',
                  border: '1px solid #444',
                  borderRadius: '4px',
                  fontSize: '0.8rem',
                  color: image.imageBase64 ? '#ddd' : '#666',
                  cursor: image.imageBase64 ? 'pointer' : 'not-allowed',
                }}
              >
                {engine.name}
              </button>
            ))}
          </div>
          <span style={{ padding: '0.5rem 1rem', backgroundColor: '#2a2a2a', borderRadius: '4px', fontSize: '0.9rem', color: '#aaa' }}>
            {annotationCount} annotations
          </span>
        </div>
      </div>
      {reverseSearchStatus && (
        <div style={{
          marginTop: '0.5rem',
          fontSize: '0.8rem',
          color: reverseSearchStatus.startsWith('Copy failed') ? '#f87171' : '#10b981',
        }}>
          {reverseSearchStatus}
        </div>
      )}
    </div>
  )
}
