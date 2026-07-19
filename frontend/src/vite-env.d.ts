/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_ROADLENS_CONFIG_PATH?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
