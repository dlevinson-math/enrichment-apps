// Home page: filter the app cards by grade and search text, and track the section in view.
(function () {
  var cards = [].slice.call(document.querySelectorAll('a.card'));
  var sections = [].slice.call(document.querySelectorAll('main section'));
  var chips = [].slice.call(document.querySelectorAll('.chip'));
  var jumps = [].slice.call(document.querySelectorAll('.jump'));
  var input = document.getElementById('q');
  var status = document.getElementById('status');
  var none = document.getElementById('none');
  var bar = document.querySelector('.bar');
  var topLink = document.querySelector('.top');
  var grades = chips.map(function (c) { return c.dataset.grade; });
  var KEY = 'enrichment-apps:grade';

  function stored() { try { return localStorage.getItem(KEY) || ''; } catch (e) { return ''; } }
  function store(v) { try { v ? localStorage.setItem(KEY, v) : localStorage.removeItem(KEY); } catch (e) {} }

  var params = new URLSearchParams(location.search);
  var grade = params.has('grade') ? params.get('grade') : stored();
  if (grades.indexOf(grade) < 0) grade = '';
  var q = params.get('q') || '';
  input.value = q;

  cards.forEach(function (c) { c._text = c.textContent.toLowerCase(); });
  sections.forEach(function (s) {
    s._count = s.querySelector('h2 small');
    s._cards = [].slice.call(s.querySelectorAll('a.card'));
    s._jump = document.querySelector('.jump[href="#' + s.id + '"]');
  });

  function plural(n) { return n + ' app' + (n === 1 ? '' : 's'); }

  function apply() {
    var words = q.toLowerCase().split(/\s+/).filter(Boolean);
    var filtering = !!(grade || words.length);
    var total = 0;
    cards.forEach(function (c) {
      var ok = (!grade || c.dataset.grade === grade) && words.every(function (w) { return c._text.indexOf(w) >= 0; });
      c.hidden = !ok;
      if (ok) total++;
    });
    sections.forEach(function (s) {
      var n = s._cards.filter(function (c) { return !c.hidden; }).length;
      s.hidden = filtering && n === 0;
      if (s._count && s._cards.length) s._count.textContent = plural(n);
      if (s._jump) s._jump.classList.toggle('off', s.hidden);
    });
    chips.forEach(function (c) { c.setAttribute('aria-pressed', String(c.dataset.grade === grade)); });
    var label = grade ? (grade === 'K' ? 'Kindergarten' : grade) : '';
    status.firstElementChild.textContent = filtering
      ? 'Showing ' + plural(total) + (label ? ' for ' + label : '') + (words.length ? ' matching “' + q.trim() + '”' : '')
      : 'All ' + plural(cards.length) + ', grouped by week, project and chapter.';
    status.lastElementChild.hidden = !filtering;
    none.hidden = total > 0;
    var p = new URLSearchParams();
    if (grade) p.set('grade', grade);
    if (words.length) p.set('q', q.trim());
    var s = p.toString();
    history.replaceState(null, '', location.pathname + (s ? '?' + s : '') + location.hash);
  }

  chips.forEach(function (c) {
    c.addEventListener('click', function () { grade = c.dataset.grade; store(grade); apply(); });
  });
  input.addEventListener('input', function () { q = input.value; apply(); });
  input.addEventListener('keydown', function (e) { if (e.key === 'Escape') { input.value = q = ''; apply(); } });
  status.lastElementChild.addEventListener('click', function () { grade = ''; store(''); input.value = q = ''; apply(); });
  document.addEventListener('keydown', function (e) {
    if (e.key === '/' && document.activeElement !== input && !e.ctrlKey && !e.metaKey) { e.preventDefault(); input.focus(); }
  });

  // Keep section headings clear of the sticky bar, and mark the section being read.
  function measure() { document.documentElement.style.setProperty('--bar-h', (bar.offsetHeight + 12) + 'px'); }
  var ticking = false;
  function onScroll() {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(function () {
      ticking = false;
      var edge = bar.getBoundingClientRect().bottom + 24;
      bar.classList.toggle('stuck', bar.getBoundingClientRect().top <= 0);
      topLink.hidden = window.scrollY < 700;
      var current = null;
      sections.forEach(function (s) { if (!s.hidden && s.getBoundingClientRect().top <= edge) current = s; });
      if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4) {
        // At the very bottom the last sections can't reach the top: prefer the one just jumped to.
        var target = location.hash && document.getElementById(location.hash.slice(1));
        var shown = sections.filter(function (s) { return !s.hidden; });
        var inView = target && shown.indexOf(target) >= 0 && target.getBoundingClientRect().top < window.innerHeight;
        current = inView ? target : (window.scrollY > 0 && shown[shown.length - 1]) || current;
      }
      jumps.forEach(function (j) {
        var on = !!current && j === current._jump;
        if (on && !j.classList.contains('here')) {
          var row = j.parentNode;
          row.scrollLeft += j.getBoundingClientRect().left - row.getBoundingClientRect().left - row.clientWidth / 2;
        }
        j.classList.toggle('here', on);
      });
    });
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  window.addEventListener('resize', function () { measure(); onScroll(); });

  [].forEach.call(document.querySelectorAll('.needs-js'), function (el) { el.hidden = false; });
  measure();
  apply();
  onScroll();
})();
