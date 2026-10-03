"""Camera-only middle mouse navigation for the exported vis-network viewer.

The exporter inserts this plain JavaScript once after creating ``container`` and
``network``. Its closure owns only a temporary pointer gesture and inline styles;
the existing viewer retains wheel zoom, graph data, filters and node selection.
"""

MIDDLE_PAN_SCRIPT = r"""
// Own middle mouse gestures before vis-network or browser autoscroll sees them.
// Camera coordinates are world units; pointer coordinates are client pixels.
(() => {
  let drag = null;
  const captureOptions = { capture: true, passive: false };
  const middleHeld = event => Number.isInteger(event.buttons) && (event.buttons & 4) !== 0;
  const matching = event => drag && event.pointerType === 'mouse' && event.pointerId === drag.id;
  const finitePoint = point => point && Number.isFinite(point.x) && Number.isFinite(point.y);
  const finiteClient = event => Number.isFinite(event.clientX) && Number.isFinite(event.clientY);
  const consume = event => {
    event.preventDefault();
    event.stopImmediatePropagation();
  };

  // Clear ownership before releasing capture: lostpointercapture may fire while
  // release is running. Missing/failed capture still has window-level cleanup.
  const finish = () => {
    if (!drag) return;
    const previous = drag;
    drag = null;
    container.style.cursor = previous.cursor;
    container.style.userSelect = previous.userSelect;
    if (previous.captured && typeof container.releasePointerCapture === 'function') {
      try { container.releasePointerCapture(previous.id); } catch (_) { /* Already lost. */ }
    }
  };

  const camera = () => {
    try {
      const scale = network.getScale();
      const position = network.getViewPosition();
      return Number.isFinite(scale) && scale > 0 && finitePoint(position)
        ? { scale, position } : null;
    } catch (_) {
      return null;
    }
  };

  container.addEventListener('pointerdown', event => {
    if (event.pointerType !== 'mouse' || event.button !== 1 || drag) return;
    consume(event);
    if (!middleHeld(event) || !finiteClient(event) || !Number.isInteger(event.pointerId)
        || event.pointerId < 0 || !camera()) return;
    drag = {
      id: event.pointerId, x: event.clientX, y: event.clientY,
      cursor: container.style.cursor, userSelect: container.style.userSelect,
      captured: false,
    };
    container.style.cursor = 'grabbing';
    container.style.userSelect = 'none';
    if (typeof container.setPointerCapture === 'function') {
      try {
        container.setPointerCapture(event.pointerId);
        drag.captured = true;
      } catch (_) { /* Window listeners cover browsers without pointer capture. */ }
    }
  }, captureOptions);

  // Window capture handles movement outside the graph even if capture failed.
  // Read the current scale each time so native wheel zoom remains authoritative.
  window.addEventListener('pointermove', event => {
    if (!matching(event)) return;
    if (!middleHeld(event)) { finish(); return; }
    consume(event);
    const current = camera();
    if (!finiteClient(event) || !current) { finish(); return; }
    const dx = event.clientX - drag.x, dy = event.clientY - drag.y;
    const position = {
      x: current.position.x - dx / current.scale,
      y: current.position.y - dy / current.scale,
    };
    if (!finitePoint(position)) { finish(); return; }
    if (dx === 0 && dy === 0) return;
    try {
      network.moveTo({ position, scale: current.scale, animation: false });
      drag.x = event.clientX;
      drag.y = event.clientY;
    } catch (_) { finish(); }
  }, captureOptions);

  window.addEventListener('pointerup', event => {
    if (!matching(event) || (event.button !== 1 && middleHeld(event))) return;
    consume(event);
    finish();
  }, captureOptions);
  window.addEventListener('pointercancel', event => {
    if (!matching(event)) return;
    consume(event);
    finish();
  }, captureOptions);
  container.addEventListener('lostpointercapture', event => {
    if (matching(event)) finish();
  }, captureOptions);
  window.addEventListener('blur', finish);
  window.addEventListener('pagehide', finish);

  // Suppress only the middle compatibility events and selection during our
  // gesture. No wheel, left/right mouse, keyboard or touch handler is replaced.
  for (const type of ['mousedown', 'auxclick']) {
    container.addEventListener(type, event => {
      if (event.button === 1) consume(event);
    }, captureOptions);
  }
  container.addEventListener('selectstart', event => {
    if (drag) consume(event);
  }, captureOptions);
})();
"""
