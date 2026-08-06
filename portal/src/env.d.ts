/// <reference types="astro/client" />

interface ImportMetaEnv {
  readonly PUBLIC_PATTERN_TRANSLATOR_URL?: string;
  readonly PUBLIC_STITCH_TRANSLATOR_URL?: string;
  readonly PUBLIC_SHOW_FUTURE_TOOLS?: string;
  readonly PUBLIC_SHOW_AD_BAR?: string;
  readonly PUBLIC_PLAUSIBLE_SCRIPT_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
