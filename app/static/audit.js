(function () {
  var btn = document.getElementById('verify-btn');
  var out = document.getElementById('verify-result');
  btn.addEventListener('click', function () {
    btn.disabled = true;
    btn.textContent = 'Verifying…';
    fetch('/api/audit/verify').then(function (r) { return r.json(); }).then(function (res) {
      out.hidden = false;
      if (res.ok) {
        out.className = 'callout ok';
        out.innerHTML = '<h2>Log intact</h2><p>All ' + res.entries + ' entries on this server match their recorded fingerprints. Nothing has been changed or removed from the middle of the log.</p>';
      } else {
        out.className = 'callout bad';
        out.innerHTML = '<h2>Log has been changed</h2><p>Entry #' + res.broken_at + ' no longer matches its fingerprint, or the chain is broken there. Entries from that point on cannot be trusted.</p>';
      }
    }).catch(function () {
      out.hidden = false;
      out.className = 'callout bad';
      out.innerHTML = '<h2>Could not verify</h2><p>The server did not respond. Try again.</p>';
    }).finally(function () {
      btn.disabled = false;
      btn.textContent = 'Verify log';
    });
  });

  var table = document.getElementById('audit-table');
  if (!table) return;
  var rows = Array.prototype.slice.call(table.tBodies[0].rows);
  var q = document.getElementById('f-q'), scan = document.getElementById('f-scan'),
      who = document.getElementById('f-who'), action = document.getElementById('f-action');
  var count = document.getElementById('audit-count'), empty = document.getElementById('audit-empty'),
      more = document.getElementById('more-btn');
  var PAGE = 100, shown = PAGE;

  function apply() {
    var text = q.value.trim().toLowerCase(), matches = 0, visible = 0;
    rows.forEach(function (r) {
      var ok = (!scan.value || r.dataset.scan === scan.value) &&
               (!who.value || r.dataset.who === who.value) &&
               (!action.value || r.dataset.action === action.value) &&
               (!text || r.dataset.text.indexOf(text) !== -1);
      if (ok) { matches++; r.hidden = matches > shown; if (!r.hidden) visible++; } else { r.hidden = true; }
    });
    count.textContent = 'Showing ' + visible + ' of ' + matches + (matches === 1 ? ' entry' : ' entries') + (matches !== rows.length ? ' (' + rows.length + ' in total)' : '');
    empty.hidden = matches !== 0;
    table.parentNode.hidden = matches === 0;
    more.hidden = matches <= shown;
  }
  [q, scan, who, action].forEach(function (el) {
    el.addEventListener('input', function () { shown = PAGE; apply(); });
    el.addEventListener('change', function () { shown = PAGE; apply(); });
  });
  more.addEventListener('click', function () { shown += PAGE; apply(); });
  document.getElementById('f-clear').addEventListener('click', function () {
    q.value = ''; scan.value = ''; who.value = ''; action.value = ''; shown = PAGE; apply();
  });
  apply();
})();
