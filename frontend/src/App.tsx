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

function App() {
  const [view, setView] = useState<View>('annotate')
  const [editImageId, setEditImageId] = useState<string | null>(null)

  const handleEditImage = (imageId: string) => {
    setEditImageId(imageId)
    setView('annotate')
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
            <p className="text-sm text-gray-400 tracking-widest mb-4 opacity-80">
              Manual bbox annotation for YOLO training data
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
            {view === 'annotate' && <AnnotationInterface editImageId={editImageId} onEditComplete={() => setEditImageId(null)} />}
            {view === 'dashboard' && <QualityDashboard onEditImage={handleEditImage} />}
          </main>
        </div>
      </div>
    </ErrorBoundary>
  )
}

export default App
