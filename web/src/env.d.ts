interface ImportMetaEnv {
  /** "0" turns off the MSW demo data (DECISIONS 2026-10-14 · M0.5). */
  readonly VITE_DEMO_DATA?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
