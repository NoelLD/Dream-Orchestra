import type { ApiClient } from './contract'
import { createMockClient } from './mockClient'
import { resolveApiMode } from './mode'
import { createRealClient } from './realClient'

export const apiMode = resolveApiMode(import.meta.env.VITE_API_MODE)

export const api: ApiClient = apiMode === 'mock' ? createMockClient() : createRealClient()
