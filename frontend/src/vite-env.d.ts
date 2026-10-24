/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base path of the ICD API on the dashboard's own origin. Defaults to "/api". */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
