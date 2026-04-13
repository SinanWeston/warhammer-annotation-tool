import React from 'react'
import ReactDOM from 'react-dom/client'
import { createHashRouter, RouterProvider, Navigate } from 'react-router-dom'
import AppLayout from './layouts/AppLayout'
import ScanPage from './pages/ScanPage'
import ResultsPage from './pages/ResultsPage'
import ArmyBuilderPage from './pages/ArmyBuilderPage'
import HistoryPage from './pages/HistoryPage'
import './index.css'

const router = createHashRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <Navigate to="/scan" replace /> },
      { path: 'scan', element: <ScanPage /> },
      { path: 'results/:scanId?', element: <ResultsPage /> },
      { path: 'army', element: <ArmyBuilderPage /> },
      { path: 'history', element: <HistoryPage /> },
    ],
  },
])

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>
)
