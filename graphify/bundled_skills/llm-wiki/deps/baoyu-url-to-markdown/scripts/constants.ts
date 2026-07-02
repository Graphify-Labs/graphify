import { resolveUrlToMarkdownChromeProfileDir } from "./paths.js";

export const DEFAULT_USER_AGENT =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36";

export const USER_DATA_DIR = resolveUrlToMarkdownChromeProfileDir();

export const DEFAULT_TIMEOUT_MS = 30_000;
export const CDP_CONNECT_TIMEOUT_MS = 15_000;
export const NETWORK_IDLE_TIMEOUT_MS = 1_500;
export const POST_LOAD_DELAY_MS = 800;
export const SCROLL_STEP_WAIT_MS = 600;
export const SCROLL_MAX_STEPS = 8;
