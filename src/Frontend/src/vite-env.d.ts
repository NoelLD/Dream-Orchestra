/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "mock" | "real" – keine Secrets in VITE_*-Variablen (N1)! */
  readonly VITE_API_MODE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
