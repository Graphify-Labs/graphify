import os from "node:os";
import path from "node:path";
import process from "node:process";

const APP_DATA_DIR = "baoyu-skills";
const URL_TO_MARKDOWN_DATA_DIR = "url-to-markdown";
const PROFILE_DIR_NAME = "chrome-profile";

export function resolveUserDataRoot(): string {
  if (process.platform === "win32") {
    return process.env.APPDATA ?? path.join(os.homedir(), "AppData", "Roaming");
  }
  if (process.platform === "darwin") {
    return path.join(os.homedir(), "Library", "Application Support");
  }
  return process.env.XDG_DATA_HOME ?? path.join(os.homedir(), ".local", "share");
}

export function resolveUrlToMarkdownDataDir(): string {
  const override = process.env.URL_DATA_DIR?.trim();
  if (override) return path.resolve(override);
  return path.join(process.cwd(), URL_TO_MARKDOWN_DATA_DIR);
}

export function resolveUrlToMarkdownChromeProfileDir(): string {
  const override = process.env.BAOYU_CHROME_PROFILE_DIR?.trim() || process.env.URL_CHROME_PROFILE_DIR?.trim();
  if (override) return path.resolve(override);
  return path.join(resolveUserDataRoot(), APP_DATA_DIR, PROFILE_DIR_NAME);
}
