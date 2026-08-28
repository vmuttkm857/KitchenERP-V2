import { FormEvent, useState } from 'react'

import { useAuth } from '../../auth/AuthContext'


export function LoginPage() {
  const { login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setIsSubmitting(true)
    try {
      await login(username, password)
      setPassword('')
    } catch {
      setError('帳號或密碼不正確。')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className="shell">
      <form className="card auth-form" onSubmit={submit}>
        <p className="eyebrow">KitchenERP V2</p>
        <h1>登入</h1>
        <label>
          帳號
          <input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" required />
        </label>
        <label>
          密碼
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required />
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        <button type="submit" disabled={isSubmitting}>{isSubmitting ? '登入中…' : '登入'}</button>
      </form>
    </main>
  )
}
