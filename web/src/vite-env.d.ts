/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Absolute origin of the elfagent API. Empty in dev (Vite proxies /api). */
  readonly VITE_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
