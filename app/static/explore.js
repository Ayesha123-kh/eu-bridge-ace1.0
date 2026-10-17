(function () {
  var form = document.getElementById('explore-form');
  var results = document.getElementById('results');
  var timer = null;

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function radio(name) { var el = form.querySelector('input[name="' + name + '"]:checked'); return el ? el.value : ''; }
  function offers() { return Array.prototype.map.call(form.querySelectorAll('input[name="offers"]:checked'), function (e) { return e.value; }); }

  function card(r, open) {
    var h = '<article class="reg ' + r.level + '"><div class="reg-head"><h3>' + esc(r.name) + '</h3>' +
      '<span class="pill ' + (r.level === 'applies' ? 'approved' : 'waiting') + '">' + (r.level === 'applies' ? 'Applies to you' : 'Check this') + '</span></div>' +
      '<div class="law">' + esc(r.full) + '</div><p>' + esc(r.summary) + '</p>' +
      '<ul class="why">' + r.why.map(function (w) { return '<li>' + esc(w) + '</li>'; }).join('') + '</ul>' +
      '<details' + (open ? ' open' : '') + '><summary>What it asks of you and when</summary>' +
      '<h4>What it asks of you</h4><ul>' + r.asks.map(function (a) { return '<li>' + esc(a) + '</li>'; }).join('') + '</ul>' +
      '<h4>Key dates</h4><ul>' + r.dates.map(function (d) { return '<li>' + esc(d) + '</li>'; }).join('') + '</ul>' +
      (r.footnote ? '<p class="note">' + esc(r.footnote) + '</p>' : '') +
      '<h4>Penalties</h4><p>' + esc(r.penalty) + '</p>' +
      '<h4>EU-Bridge</h4><p>' + esc(r.eubridge) + '</p>' +
      '<p><a href="' + esc(r.url) + '" target="_blank" rel="noopener">Read the official text</a></p></details></article>';
    return h;
  }

  function render(data) {
    var h = '';
    if (data.outside_eu) {
      h += '<div class="callout warn"><h2>You said you have no EU customers</h2><p>EU rules mostly apply when you offer products or services to people in the EU, or handle their data. The rules below apply if you launch there.</p></div>';
    }
    var applies = data.results.filter(function (r) { return r.level === 'applies'; });
    var check = data.results.filter(function (r) { return r.level !== 'applies'; });
    if (!data.results.length) {
      h += '<div class="callout" id="placeholder"><h2>Pick what you offer</h2><p>Choose one or more options on the left. The rules that fit show up here.</p></div>';
    } else {
      h += '<p class="count"><strong>' + applies.length + '</strong> ' + (applies.length === 1 ? 'rule applies' : 'rules apply') + ' to you' +
        (check.length ? ' and <strong>' + check.length + '</strong> ' + (check.length === 1 ? 'is' : 'are') + ' worth checking' : '') + '.</p>';
      applies.forEach(function (r, i) { h += card(r, i === 0); });
      if (check.length) {
        h += '<h2 class="subhead">Worth checking</h2>';
        check.forEach(function (r) { h += card(r, false); });
      }
      if (data.not_matched.length) {
        h += '<p class="others">Not matched by your answers: ' + data.not_matched.map(function (n) { return esc(n.name); }).join(', ') + '.</p>';
      }
    }
    results.innerHTML = h;

    Array.prototype.forEach.call(document.querySelectorAll('.tier'), function (t) {
      var mine = data.ai_tiers.indexOf(t.dataset.tier) !== -1;
      t.classList.toggle('on', mine);
      t.querySelector('.mine').hidden = !mine;
    });
  }

  function update() {
    var body = {
      offers: offers(),
      eu_users: radio('eu_users'),
      size: document.getElementById('size').value,
      personal_data: radio('personal') === 'yes'
    };
    fetch('/api/regulations/match', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(function (r) { if (!r.ok) throw new Error(); return r.json(); })
      .then(render)
      .catch(function () {
        results.innerHTML = '<div class="callout bad"><h2>Could not load the results</h2><p>Check your connection and change an answer to try again.</p></div>';
      });
  }

  form.addEventListener('change', function () { clearTimeout(timer); timer = setTimeout(update, 60); });
  form.addEventListener('submit', function (e) { e.preventDefault(); });
})();
