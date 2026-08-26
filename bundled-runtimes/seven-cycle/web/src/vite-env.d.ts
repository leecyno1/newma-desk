/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_VIBEDESK_PARENT_ORIGIN?: string
  readonly VITE_NEWMA_DESK_PARENT_ORIGIN?: string
  readonly VITE_NEWMA_DOCK_PARENT_ORIGIN?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
