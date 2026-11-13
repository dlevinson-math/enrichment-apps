// Loaded by every app page: a small tab on the right edge that leads back to the list of all apps.
// It rests in the bottom corner and moves up the edge when a button or other control is underneath it.
(function () {
  if (window.top !== window.self || document.getElementById('all-apps-link')) return;
  var SIZE = 44, MARGIN = 10, STEP = 54;
  var a = document.createElement('a');
  a.id = 'all-apps-link';
  a.href = '../../';
  a.setAttribute('aria-label', 'All enrichment apps');
  a.title = 'All enrichment apps';
  a.innerHTML = '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 11.5 12 4l9 7.5"/><path d="M5.5 10v9.5h13V10"/><path d="M10 19.5v-5h4v5"/></svg><span>All apps</span>';
  var css = document.createElement('style');
  css.textContent =
    '#all-apps-link{position:fixed;right:0;bottom:' + MARGIN + 'px;z-index:2147483000;box-sizing:border-box;display:flex;align-items:center;gap:8px;' +
    'height:' + SIZE + 'px;padding:0 8px 0 10px;background:#E6C84B;color:#22211F;border:2px solid #22211F;border-right:0;border-radius:22px 0 0 22px;' +
    'font:700 15px/1 "Segoe UI",system-ui,-apple-system,sans-serif;text-decoration:none;opacity:.65;transition:opacity .15s,bottom .2s}' +
    '#all-apps-link span{display:none;white-space:nowrap}' +
    '#all-apps-link:hover,#all-apps-link:focus-visible{opacity:1}' +
    '#all-apps-link:hover span,#all-apps-link:focus-visible span{display:inline}' +
    '#all-apps-link:focus-visible{outline:3px solid #22211F;outline-offset:2px}' +
    '@media (prefers-reduced-motion:reduce){#all-apps-link{transition:none}}' +
    '@media print{#all-apps-link{display:none}}';
  document.head.appendChild(css);
  document.body.appendChild(a);

  var CONTROL = 'button,a,input,select,textarea,label,summary,[role=button],[role=tab],[onclick],[draggable=true]';
  function busy(bottom) {
    var w = window.innerWidth, top = window.innerHeight - bottom - SIZE;
    for (var x = w - SIZE + 4; x < w; x += 12) {
      for (var y = top + 2; y < top + SIZE; y += 10) {
        var els = document.elementsFromPoint(x, y);
        for (var i = 0; i < els.length; i++) {
          var el = els[i];
          if (el === a || a.contains(el)) continue;
          var cursor = getComputedStyle(el).cursor;
          if (el.closest(CONTROL) || cursor === 'pointer' || cursor === 'grab') return true;
          break; // only the topmost thing under the tab matters
        }
      }
    }
    return false;
  }
  function place() {
    if (a.matches(':hover') || document.activeElement === a) return;
    var limit = window.innerHeight * 0.6, bottom = MARGIN;
    while (bottom < limit && busy(bottom)) bottom += STEP;
    a.style.bottom = (bottom < limit ? bottom : MARGIN) + 'px';
  }
  var timer;
  function soon() { clearTimeout(timer); timer = setTimeout(place, 250); }
  window.addEventListener('scroll', soon, { passive: true, capture: true });
  window.addEventListener('resize', soon);
  document.addEventListener('click', soon, true);
  place();
  setTimeout(place, 1200);
})();
