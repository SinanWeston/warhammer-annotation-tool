import { useState } from 'react'
import HomePage from './pages/HomePage'
import AnnotatePage from './pages/AnnotatePage'

type Page = 'home' | 'annotate'

export default function App() {
  const [page, setPage] = useState<Page>('home')

  return (
    <div className="flex flex-col min-h-[100dvh]">
      {page === 'home' && (
        <HomePage onStartAnnotating={() => setPage('annotate')} />
      )}
      {page === 'annotate' && (
        <AnnotatePage onBack={() => setPage('home')} />
      )}
    </div>
  )
}
