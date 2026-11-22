import { useQuery } from '@tanstack/react-query'
import { api } from './client'

/** Modus des Backends (mock | sim | real) für Banner und Badge (N2); im Frontend-Testmodus immer „mock“. */
export function useBackendStatus() {
  return useQuery({ queryKey: ['backend-status'], queryFn: () => api.status(), refetchInterval: 15_000, retry: false })
}
