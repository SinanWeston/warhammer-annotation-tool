import { Outlet } from 'react-router-dom'
import Header from '../components/Header'
import TabNav from '../components/TabNav'

export default function AppLayout() {
  return (
    <div className="flex flex-col min-h-screen bg-gothic-darker">
      <Header />
      <TabNav />
      <main className="flex-1 max-w-[1400px] w-full mx-auto px-6 py-6">
        <Outlet />
      </main>
    </div>
  )
}
