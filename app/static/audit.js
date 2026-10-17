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
        out.innerHTML = '<h2>Log intact</h2><p>All ' + res.entries + ' entries match their recorded fingerprints. Nothing has been changed or removed from the middle of the log.</p>';
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
})();
