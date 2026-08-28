import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'

import { apiRequest, setAccessToken, setAuthExpiredHandler } from '../api/client'
import type { AuthResponse, User } from '../types/api'


interface AuthContextValue {
  user: User | null
  isLoading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const initialized = useRef(false)

  const applyAuth = useCallback((auth: AuthResponse) => {
    setAccessToken(auth.access_token)
    setUser(auth.user)
  }, [])

  useEffect(() => {
    setAuthExpiredHandler(() => {
      setAccessToken(null)
      setUser(null)
    })
    return () => setAuthExpiredHandler(null)
  }, [])

  useEffect(() => {
    if (initialized.current) return
    initialized.current = true
    apiRequest<AuthResponse>('/auth/refresh', { method: 'POST' })
      .then(applyAuth)
      .catch(() => {
        setAccessToken(null)
        setUser(null)
      })
      .finally(() => setIsLoading(false))
  }, [applyAuth])

  const login = useCallback(async (username: string, password: string) => {
    const auth = await apiRequest<AuthResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })
    applyAuth(auth)
  }, [applyAuth])

  const logout = useCallback(async () => {
    try {
      await apiRequest('/auth/logout', { method: 'POST' })
    } finally {
      setAccessToken(null)
      setUser(null)
    }
  }, [])

  const value = useMemo(
    () => ({ user, isLoading, login, logout }),
    [user, isLoading, login, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}
