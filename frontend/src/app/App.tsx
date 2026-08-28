import { useAuth } from '../auth/AuthContext'
import { LoginPage } from '../features/auth/LoginPage'

export function App() {
  const { user, isLoading, logout } = useAuth()

  if (isLoading) return <main className="shell"><p>載入中…</p></main>
  if (!user) return <LoginPage />

  return (
    <main className="shell">
      <section className="card">
        <p className="eyebrow">KitchenERP V2</p>
        <h1>已登入：{user.display_name}</h1>
        <p>目前尚未建立 ERP 功能。</p>
        <button type="button" onClick={() => void logout()}>登出</button>
      </section>
    </main>
  )
}
