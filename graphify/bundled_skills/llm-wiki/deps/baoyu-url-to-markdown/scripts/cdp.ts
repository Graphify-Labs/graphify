import {
  CdpConnection,
  findChromeExecutable as findChromeExecutableBase,
  findExistingChromeDebugPort,
  getFreePort,
  killChrome,
  launchChrome as launchChromeBase,
  sleep,
  waitForChromeDebugPort,
  type PlatformCandidates,
} from 'baoyu-chrome-cdp';

import { resolveUrlToMarkdownChromeProfileDir } from './paths.js';
import { NETWORK_IDLE_TIMEOUT_MS } from './constants.js';

const CHROME_CANDIDATES_FULL: PlatformCandidates = {
  darwin: [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary',
    '/Applications/Google Chrome Beta.app/Contents/MacOS/Google Chrome Beta',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
  ],
  win32: [
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  ],
  default: [
    '/usr/bin/google-chrome',
    '/usr/bin/google-chrome-stable',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
    '/snap/bin/chromium',
    '/usr/bin/microsoft-edge',
  ],
};

export { CdpConnection, getFreePort, killChrome, sleep, waitForChromeDebugPort };

export async function findExistingChromePort(): Promise<number | null> {
  return await findExistingChromeDebugPort({
    profileDir: resolveUrlToMarkdownChromeProfileDir(),
  });
}

export function findChromeExecutable(): string | null {
  return findChromeExecutableBase({
    candidates: CHROME_CANDIDATES_FULL,
    envNames: ['URL_CHROME_PATH'],
  }) ?? null;
}

export async function launchChrome(url: string, port: number, headless = false) {
  const chromePath = findChromeExecutable();
  if (!chromePath) throw new Error('Chrome executable not found. Install Chrome or set URL_CHROME_PATH env.');

  return await launchChromeBase({
    chromePath,
    profileDir: resolveUrlToMarkdownChromeProfileDir(),
    port,
    url,
    headless,
    extraArgs: ['--disable-popup-blocking'],
  });
}

export async function waitForNetworkIdle(
  cdp: CdpConnection,
  sessionId: string,
  timeoutMs: number = NETWORK_IDLE_TIMEOUT_MS,
): Promise<void> {
  return new Promise((resolve) => {
    let timer: ReturnType<typeof setTimeout> | null = null;
    let pending = 0;
    const cleanup = () => {
      if (timer) clearTimeout(timer);
      cdp.off('Network.requestWillBeSent', onRequest);
      cdp.off('Network.loadingFinished', onFinish);
      cdp.off('Network.loadingFailed', onFinish);
    };
    const done = () => { cleanup(); resolve(); };
    const resetTimer = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(done, timeoutMs);
    };
    const onRequest = () => { pending++; resetTimer(); };
    const onFinish = () => { pending = Math.max(0, pending - 1); if (pending <= 2) resetTimer(); };
    cdp.on('Network.requestWillBeSent', onRequest);
    cdp.on('Network.loadingFinished', onFinish);
    cdp.on('Network.loadingFailed', onFinish);
    resetTimer();
  });
}

export async function waitForPageLoad(
  cdp: CdpConnection,
  sessionId: string,
  timeoutMs: number = 30_000,
): Promise<void> {
  void sessionId;
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      cdp.off('Page.loadEventFired', handler);
      resolve();
    }, timeoutMs);
    const handler = () => {
      clearTimeout(timer);
      cdp.off('Page.loadEventFired', handler);
      resolve();
    };
    cdp.on('Page.loadEventFired', handler);
  });
}

export async function createTargetAndAttach(
  cdp: CdpConnection,
  url: string,
): Promise<{ targetId: string; sessionId: string }> {
  const { targetId } = await cdp.send<{ targetId: string }>('Target.createTarget', { url });
  const { sessionId } = await cdp.send<{ sessionId: string }>('Target.attachToTarget', { targetId, flatten: true });
  await cdp.send('Network.enable', {}, { sessionId });
  await cdp.send('Page.enable', {}, { sessionId });
  return { targetId, sessionId };
}

export async function navigateAndWait(
  cdp: CdpConnection,
  sessionId: string,
  url: string,
  timeoutMs: number,
): Promise<void> {
  const loadPromise = new Promise<void>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Page load timeout')), timeoutMs);
    const handler = (params: unknown) => {
      const event = params as { name?: string };
      if (event.name === 'load' || event.name === 'DOMContentLoaded') {
        clearTimeout(timer);
        cdp.off('Page.lifecycleEvent', handler);
        resolve();
      }
    };
    cdp.on('Page.lifecycleEvent', handler);
  });
  await cdp.send('Page.navigate', { url }, { sessionId });
  await loadPromise;
}

export async function evaluateScript<T>(
  cdp: CdpConnection,
  sessionId: string,
  expression: string,
  timeoutMs: number = 30_000,
): Promise<T> {
  const result = await cdp.send<{ result: { value?: T } }>(
    'Runtime.evaluate',
    { expression, returnByValue: true, awaitPromise: true },
    { sessionId, timeoutMs },
  );
  return result.result.value as T;
}

export async function autoScroll(
  cdp: CdpConnection,
  sessionId: string,
  steps: number = 8,
  waitMs: number = 600,
): Promise<void> {
  let lastHeight = await evaluateScript<number>(cdp, sessionId, 'document.body.scrollHeight');
  for (let i = 0; i < steps; i++) {
    await evaluateScript<void>(cdp, sessionId, 'window.scrollTo(0, document.body.scrollHeight)');
    await sleep(waitMs);
    const newHeight = await evaluateScript<number>(cdp, sessionId, 'document.body.scrollHeight');
    if (newHeight === lastHeight) break;
    lastHeight = newHeight;
  }
  await evaluateScript<void>(cdp, sessionId, 'window.scrollTo(0, 0)');
}
