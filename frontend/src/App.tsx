/**
 * Warhammer 40K Dataset Annotation App
 *
 * Simple app for manually annotating bounding boxes on miniature images.
 * Creates training data for YOLO object detection models.
 */

import { useState } from 'react'
import ErrorBoundary from './components/ErrorBoundary'
import AnnotationInterface from './components/AnnotationInterface'
import QualityDashboard from './components/QualityDashboard'

type View = 'annotate' | 'dashboard'

const STORAGE_KEY = 'annotator_username'

function UsernameModal({ onConfirm }: { onConfirm: (name: string) => void }) {
  const [value, setValue] = useState('')
  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.85)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000
    }}>
      <div style={{
        background: '#1a1a1a', border: '2px solid #f59e0b', borderRadius: 12,
        padding: '2rem', maxWidth: 400, width: '90%', textAlign: 'center'
      }}>
        <h2 style={{ color: '#f59e0b', fontSize: '1.5rem', marginBottom: '0.5rem' }}>
          ⚔️ WHO ARE YOU?
        </h2>
        <p style={{ color: '#9ca3af', fontSize: '0.875rem', marginBottom: '1.5rem' }}>
          Enter your name so annotations are attributed to you and you're not given images someone else is working on.
        </p>
        <input
          autoFocus
          type="text"
          placeholder="e.g. sinan, dave, alice"
          value={value}
          onChange={e => setValue(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && value.trim() && onConfirm(value.trim())}
          style={{
            width: '100%', padding: '0.75rem', borderRadius: 8,
            border: '1px solid #374151', background: '#111', color: '#fff',
            fontSize: '1rem', marginBottom: '1rem', boxSizing: 'border-box'
          }}
        />
        <button
          disabled={!value.trim()}
          onClick={() => onConfirm(value.trim())}
          style={{
            width: '100%', padding: '0.75rem', borderRadius: 8,
            background: value.trim() ? '#d97706' : '#374151',
            color: '#fff', fontWeight: 'bold', fontSize: '1rem',
            border: 'none', cursor: value.trim() ? 'pointer' : 'not-allowed'
          }}
        >
          START ANNOTATING
        </button>
      </div>
    </div>
  )
}

function App() {
  const [view, setView] = useState<View>('annotate')
  const [editImageId, setEditImageId] = useState<string | null>(null)
  const [annotatorName, setAnnotatorName] = useState<string | null>(
    () => localStorage.getItem(STORAGE_KEY)
  )

  const handleConfirmName = (name: string) => {
    localStorage.setItem(STORAGE_KEY, name)
    setAnnotatorName(name)
  }

  const handleEditImage = (imageId: string) => {
    setEditImageId(imageId)
    setView('annotate')
  }

  if (!annotatorName) {
    return <UsernameModal onConfirm={handleConfirmName} />
  }

  return (
    <ErrorBoundary>
      <div className="min-h-screen bg-gray-900">
        <div className="max-w-7xl mx-auto py-8 px-4">
          {/* HEADER */}
          <header className="text-center mb-10">
            <h1 className="text-5xl font-black mb-3 text-amber-500 tracking-wider">
              ⚔️ WARHAMMER 40K ⚔️
            </h1>
            <h2 className="text-3xl font-bold mb-4 text-white">
              DATASET ANNOTATION
            </h2>
            <p style={{ fontSize: '0.8rem', color: '#6b7280', marginBottom: '0.25rem' }}>
              annotating as <span style={{ color: '#f59e0b', fontWeight: 'bold' }}>{annotatorName}</span>
              {' '}·{' '}
              <button
                onClick={() => { localStorage.removeItem(STORAGE_KEY); setAnnotatorName(null) }}
                style={{ background: 'none', border: 'none', color: '#6b7280', cursor: 'pointer', textDecoration: 'underline', fontSize: 'inherit' }}
              >
                change
              </button>
            </p>
            <div className="h-0.5 mx-auto mb-6 w-48 bg-amber-500 opacity-50" />

            {/* Navigation */}
            <div style={{ display: 'flex', justifyContent: 'center', gap: '1rem', marginTop: '1rem' }}>
              <button
                onClick={() => setView('annotate')}
                style={{
                  padding: '0.75rem 2rem',
                  backgroundColor: view === 'annotate' ? '#059669' : '#1a1a1a',
                  color: '#fff',
                  border: view === 'annotate' ? '2px solid #10b981' : '2px solid #333',
                  borderRadius: '8px',
                  fontSize: '1rem',
                  fontWeight: 'bold',
                  cursor: 'pointer',
                  transition: 'all 0.2s'
                }}
              >
                Annotation
              </button>
              <button
                onClick={() => setView('dashboard')}
                style={{
                  padding: '0.75rem 2rem',
                  backgroundColor: view === 'dashboard' ? '#7c3aed' : '#1a1a1a',
                  color: '#fff',
                  border: view === 'dashboard' ? '2px solid #a78bfa' : '2px solid #333',
                  borderRadius: '8px',
                  fontSize: '1rem',
                  fontWeight: 'bold',
                  cursor: 'pointer',
                  transition: 'all 0.2s'
                }}
              >
                Dashboard
              </button>
            </div>
          </header>

          {/* MAIN CONTENT */}
          <main>
            {view === 'annotate' && <AnnotationInterface editImageId={editImageId} onEditComplete={() => setEditImageId(null)} annotatorName={annotatorName} />}
            {view === 'dashboard' && <QualityDashboard onEditImage={handleEditImage} />}
          </main>
        </div>
      </div>
    </ErrorBoundary>
  )
}

export default App
