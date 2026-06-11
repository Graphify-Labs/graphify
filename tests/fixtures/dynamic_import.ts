import { logger } from './logger';

async function processInbound(orgId: string, phone: string) {
    const { shouldHandle, processMessage } = await import('./mayaEngine.js');
    const handle = await shouldHandle(orgId, phone);
    if (handle.sessionId) {
        await processMessage({ orgId, phone }, handle.sessionId);
    }
}

async function pollMessages(orgId: string) {
    const { commsQueue } = await import('./queue.js');
    await commsQueue.add('check-inbound', { orgId });
}

async function loadHandler(handlerName: string) {
    // dynamic template literal — path not statically resolvable, should produce no edge
    const mod = await import(`./handlers/${handlerName}`);
    return mod.default;
}

async function loadStatic() {
    // static template literal (no interpolation) — should resolve like a plain string
    const { helper } = await import(`./staticHelper`);
    return helper;
}

function syncOnly() {
    logger.info('no dynamic imports here');
}

export { processInbound, pollMessages, loadHandler, loadStatic, syncOnly };
