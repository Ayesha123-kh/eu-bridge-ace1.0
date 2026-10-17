(function () {
  var root = document.getElementById('dash');
  var data = null;
  var state = { q: '', status: 'all', source: 'all', check: 'all', sort: 'new', view: 'scans' };
  var expanded = {};

  var RISK = { possibly_high: 'Possibly high-risk', limited: 'Limited', minimal: 'Minimal', possibly_prohibited: 'Possibly prohibited' };
  var RISK_RANK = { possibly_prohibited: 4, possibly_high: 3, limited: 2, minimal: 1 };
  var SOURCE = { public: 'Public repo', private_token: 'Private repo', private_zip: 'ZIP upload', assessment: 'No-code assessment' };
  var CHECK_NAMES = { 'AIA-50-1': 'AI disclosure', 'GDPR-13': 'Third-party AI notice', 'GDPR-5-1C': 'Personal data in logs', 'AIA-RISK': 'Risk tier' };

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function plural(n, one, many) { return n + ' ' + (n === 1 ? one : many); }

  /* ---------- filtering ---------- */
  function matchStatus(s) {
    switch (state.status) {
      case 'attention': return !!s.attention;
      case 'escalated': return s.escalated;
      case 'delivered': return s.delivered;
      case 'approved': return s.approved > 0;
      case 'failed': return s.status === 'failed';
      default: return true;
    }
  }
  function filtered() {
    var q = state.q.trim().toLowerCase();
    var list = data.scans.filter(function (s) {
      return (!q || s.name.toLowerCase().indexOf(q) !== -1) && matchStatus(s) &&
        (state.source === 'all' || s.source === state.source) &&
        (state.check === 'all' || (s.per_rule[state.check] && s.per_rule[state.check].found > 0));
    });
    var sorters = {
      new: function (a, b) { return a.created_at < b.created_at ? 1 : -1; },
      old: function (a, b) { return a.created_at > b.created_at ? 1 : -1; },
      findings: function (a, b) { return b.total - a.total; },
      waiting: function (a, b) { return b.waiting - a.waiting || (a.created_at < b.created_at ? 1 : -1); }
    };
    return list.sort(sorters[state.sort]);
  }
  function filtersActive() {
    return state.q || state.status !== 'all' || state.source !== 'all' || state.check !== 'all';
  }
  function reset() { state.q = ''; state.status = 'all'; state.source = 'all'; state.check = 'all'; }

  /* ---------- pieces ---------- */
  function statTiles() {
    var st = data.stats;
    var tiles = [
      ['all', st.scans, 'Scans run'],
      ['attention', st.waiting, 'Decisions waiting'],
      ['approved', st.approved, 'Fixes approved'],
      ['delivered', st.delivered, 'Delivered as PR or download']
    ];
    return tiles.map(function (t) {
      var on = state.status === t[0] || (t[0] === 'all' && state.status === 'all' && !filtersActive());
      return '<button type="button" class="stat" data-stat="' + t[0] + '" aria-pressed="' + (state.status === t[0] && t[0] !== 'all') + '">' +
        '<span class="n">' + t[1] + '</span><span class="l">' + t[2] + '</span></button>';
    }).join('');
  }

  function chips() {
    var c = { all: data.scans.length, attention: 0, escalated: 0, delivered: 0, failed: 0 };
    data.scans.forEach(function (s) {
      if (s.attention) c.attention++;
      if (s.escalated) c.escalated++;
      if (s.delivered) c.delivered++;
      if (s.status === 'failed') c.failed++;
    });
    var defs = [['all', 'All'], ['attention', 'Needs attention'], ['escalated', 'Escalated'], ['delivered', 'Delivered'], ['failed', 'Failed']];
    return defs.map(function (d) {
      return '<button type="button" class="fchip" data-chip="' + d[0] + '" aria-pressed="' + (state.status === d[0]) + '">' + d[1] + ' <span class="cnt">' + c[d[0]] + '</span></button>';
    }).join('');
  }

  function detailRow(s) {
    var rows = ['AIA-50-1', 'GDPR-13', 'GDPR-5-1C'].map(function (r) {
      var x = s.per_rule[r];
      return '<tr><td>' + esc(CHECK_NAMES[r]) + ' <span class="code">' + r + '</span></td><td class="num">' + x.found + '</td><td class="num">' + x.approved + '</td><td class="num">' + x.rejected + '</td><td class="num">' + x.waiting + '</td></tr>';
    }).join('');
    var h = '<tr class="detail-row"><td colspan="6"><div class="detail">';
    h += '<div><h4>Findings by check</h4><table class="mini"><thead><tr><th>Check</th><th class="num">Found</th><th class="num">Approved</th><th class="num">Rejected</th><th class="num">Waiting</th></tr></thead><tbody>' + rows + '</tbody></table></div>';
    h += '<div><h4>Risk tier</h4><p>' + esc(RISK[s.risk_tier] || 'Not assessed') + (s.escalated ? (s.risk_reviewed ? ' (confirmed by a person)' : ' (needs a person to confirm)') : '') + '</p>' +
      (s.escalation_reason ? '<p class="muted">' + esc(s.escalation_reason) + '</p>' : '') +
      '<p class="detail-actions"><a class="btn small primary" href="/scans/' + esc(s.id) + '">Open review</a> <a class="btn small" href="/audit?scan=' + esc(s.id) + '">Audit entries</a></p></div>';
    return h + '</div></td></tr>';
  }

  function scansTable(list) {
    if (!list.length) return emptyResults();
    var h = '<div class="table-wrap"><table class="dtable"><thead><tr><th>Company or repository</th><th>Status</th><th>Risk tier</th><th class="num">Findings</th><th>Scanned</th><th></th></tr></thead><tbody>';
    list.forEach(function (s) {
      var open = !!expanded[s.id];
      h += '<tr class="row' + (open ? ' open' : '') + '" data-row="' + esc(s.id) + '"><td><a href="/scans/' + esc(s.id) + '">' + esc(s.name) + '</a><span class="tag">' + esc(SOURCE[s.source] || s.source) + '</span></td>' +
        '<td>' + esc(s.status_label) + (s.attention ? '<div class="why">' + esc(s.attention) + '</div>' : '') + '</td>' +
        '<td>' + esc(RISK[s.risk_tier] || '—') + '</td>' +
        '<td class="num">' + s.total + (s.waiting ? ' <span class="muted">(' + s.waiting + ' waiting)</span>' : '') + '</td>' +
        '<td class="nowrap">' + esc(s.when) + '</td>' +
        '<td class="num"><button type="button" class="linkbtn" data-toggle="' + esc(s.id) + '" aria-expanded="' + open + '">' + (open ? 'Hide details' : 'Details') + '</button></td></tr>';
      if (open) h += detailRow(s);
    });
    return h + '</tbody></table></div>';
  }

  function companiesTable(list) {
    if (!list.length) return emptyResults();
    var groups = {};
    list.forEach(function (s) { (groups[s.company] = groups[s.company] || []).push(s); });
    var names = Object.keys(groups).sort(function (a, b) { return groups[b][0].created_at < groups[a][0].created_at ? -1 : 1; });
    var h = '<div class="table-wrap"><table class="dtable"><thead><tr><th>Company or repository</th><th class="num">Scans</th><th>Latest scan</th><th>Highest risk</th><th class="num">Waiting</th><th></th></tr></thead><tbody>';
    names.forEach(function (n) {
      var g = groups[n], latest = g[0];
      g.forEach(function (s) { if (s.created_at > latest.created_at) latest = s; });
      var risk = g.reduce(function (m, s) { return (RISK_RANK[s.risk_tier] || 0) > (RISK_RANK[m] || 0) ? s.risk_tier : m; }, null);
      var open = !!expanded['c:' + n];
      h += '<tr class="row' + (open ? ' open' : '') + '"><td><strong>' + esc(n) + '</strong></td><td class="num">' + g.length + '</td><td class="nowrap">' + esc(latest.when) + '</td><td>' + esc(RISK[risk] || '—') + '</td>' +
        '<td class="num">' + g.reduce(function (a, s) { return a + s.waiting; }, 0) + '</td>' +
        '<td class="num"><button type="button" class="linkbtn" data-toggle="c:' + esc(n) + '" aria-expanded="' + open + '">' + (open ? 'Hide history' : 'History') + '</button></td></tr>';
      if (open) {
        h += '<tr class="detail-row"><td colspan="6"><div class="detail"><div style="grid-column:1/-1"><h4>Scan history</h4><ul class="hist">' +
          g.map(function (s) { return '<li><a href="/scans/' + esc(s.id) + '">' + esc(s.when) + '</a> · ' + esc(s.status_label) + ' · ' + esc(RISK[s.risk_tier] || '—') + ' · ' + plural(s.total, 'finding', 'findings') + '</li>'; }).join('') +
          '</ul><p class="detail-actions"><a class="btn small" href="/audit?scan=' + esc(latest.id) + '">Audit entries</a></p></div></div></td></tr>';
      }
    });
    return h + '</tbody></table></div>';
  }

  function emptyResults() {
    return '<div class="callout"><h2>No scans match these filters</h2><p><button type="button" class="linkbtn" data-reset="1">Clear filters</button> to see all ' + data.scans.length + '.</p></div>';
  }

  function checksPanel() {
    var h = '<div class="checkrows">';
    data.checks.forEach(function (c) {
      var on = state.check === c.rule;
      var tot = c.found || 1;
      h += '<button type="button" class="checkrow" data-check="' + c.rule + '" aria-pressed="' + on + '"><div class="top"><strong>' + esc(c.name) + '</strong><span class="count">' + c.found + ' found</span></div>' +
        '<div class="stack" role="img" aria-label="' + c.approved + ' approved, ' + c.rejected + ' rejected, ' + c.waiting + ' waiting">' +
        (c.found ? '<i class="ok" style="width:' + (100 * c.approved / tot) + '%"></i><i class="rej" style="width:' + (100 * c.rejected / tot) + '%"></i><i class="wait" style="width:' + (100 * c.waiting / tot) + '%"></i>' : '') +
        '</div><div class="sub">' + c.approved + ' approved · ' + c.rejected + ' rejected · ' + c.waiting + ' waiting</div></button>';
    });
    h += '<div class="checkrow static"><div class="top"><strong>Risk tier</strong><span class="count">' + data.risk.escalated + ' escalated</span></div><div class="sub">' + data.risk.confirmed + ' of ' + data.risk.escalated + ' confirmed by a person</div></div>';
    return h + '</div>';
  }

  function activityPanel() {
    if (!data.activity.length) return '<p class="muted">No activity yet.</p>';
    return '<ul class="activity">' + data.activity.map(function (e) {
      return '<li><div class="what">' + (e.scan_id ? '<a href="/audit?scan=' + esc(e.scan_id) + '">' + esc(e.action) + '</a>' : esc(e.action)) + '</div><div class="meta">' + esc(e.actor) + ' · ' + esc(e.when) + '</div>' +
        (e.summary ? '<div class="sum">' + esc(e.summary) + '</div>' : '') + '</li>';
    }).join('') + '</ul>' +
      '<p class="integrity ' + (data.integrity.ok ? 'ok' : 'bad') + '">' + (data.integrity.ok ? 'Audit log intact (' + data.integrity.entries + ' entries on this server).' : 'Audit log has been changed at entry #' + data.integrity.broken_at + '.') + ' <a href="/audit">Open the audit log</a></p>';
  }

  function attentionPanel() {
    var list = data.scans.filter(function (s) { return s.attention; }).slice(0, 5);
    if (!list.length) return '<p class="empty">Nothing is waiting for a decision.</p>';
    return '<ul class="attention">' + list.map(function (s) {
      return '<li><div><strong>' + esc(s.name) + '</strong><span class="why">' + esc(s.attention) + '</span></div><a class="btn small" href="/scans/' + esc(s.id) + '">Continue review</a></li>';
    }).join('') + '</ul>';
  }

  /* ---------- layout ---------- */
  function build() {
    if (!data.scans.length) {
      root.innerHTML = '<section class="panel emptystate"><h2>No scans yet</h2><p>Scan a repository, upload your code, or run a no-code assessment. EU-Bridge drafts fixes for EU AI Act and GDPR issues, and you approve each one before anything is changed.</p><p><a class="btn primary" href="/new">Run your first scan</a> <a class="btn" href="/explore">Explore EU regulations</a></p></section>';
      return;
    }
    root.innerHTML =
      '<section class="stats" id="stats" aria-label="Summary"></section>' +
      '<section class="block"><h2>Needs your attention</h2><div id="attention"></div></section>' +
      '<section class="block"><div class="resulthead"><h2>Scan history</h2>' +
      '<div class="seg" role="group" aria-label="View"><button type="button" data-view="scans" aria-pressed="true">Scans</button><button type="button" data-view="companies" aria-pressed="false">Companies</button></div></div>' +
      '<div class="filters"><div class="fgroup grow"><label for="d-q">Search</label><input id="d-q" type="search" placeholder="Search by company or repository"></div>' +
      '<div class="fgroup"><label for="d-source">Source</label><select id="d-source"><option value="all">All sources</option><option value="public">Public repo</option><option value="private_token">Private repo</option><option value="private_zip">ZIP upload</option><option value="assessment">No-code assessment</option></select></div>' +
      '<div class="fgroup"><label for="d-check">Finding type</label><select id="d-check"><option value="all">Any check</option><option value="AIA-50-1">AI disclosure</option><option value="GDPR-13">Third-party AI notice</option><option value="GDPR-5-1C">Personal data in logs</option></select></div>' +
      '<div class="fgroup"><label for="d-sort">Sort</label><select id="d-sort"><option value="new">Newest first</option><option value="old">Oldest first</option><option value="waiting">Most waiting</option><option value="findings">Most findings</option></select></div></div>' +
      '<div class="chiprow" id="chips"></div><p class="count" id="count" aria-live="polite"></p><div id="results"></div></section>' +
      '<div class="two"><section class="block"><h2>Findings by check</h2><p class="legend"><span class="k ok"></span>Approved <span class="k rej"></span>Rejected <span class="k wait"></span>Waiting</p><div id="checks"></div></section>' +
      '<section class="block"><h2>Recent activity</h2><div id="activity"></div></section></div>';
    document.getElementById('attention').innerHTML = attentionPanel();
    document.getElementById('activity').innerHTML = activityPanel();
    update();
  }

  function update() {
    document.getElementById('stats').innerHTML = statTiles();
    document.getElementById('chips').innerHTML = chips();
    document.getElementById('checks').innerHTML = checksPanel();
    var list = filtered();
    document.getElementById('results').innerHTML = state.view === 'scans' ? scansTable(list) : companiesTable(list);
    document.getElementById('count').innerHTML = 'Showing <strong>' + list.length + '</strong> of ' + data.scans.length + ' scans' +
      (filtersActive() ? ' · <button type="button" class="linkbtn" data-reset="1">Clear filters</button>' : '');
    Array.prototype.forEach.call(root.querySelectorAll('[data-view]'), function (b) { b.setAttribute('aria-pressed', String(b.dataset.view === state.view)); });
    var q = document.getElementById('d-q');
    if (q && q.value !== state.q) q.value = state.q;
    ['source', 'check', 'sort'].forEach(function (k) { var el = document.getElementById('d-' + k); if (el && el.value !== state[k]) el.value = state[k]; });
  }

  /* ---------- events ---------- */
  root.addEventListener('click', function (e) {
    var t = e.target.closest('button');
    if (!t) return;
    if (t.dataset.stat) { reset(); if (t.dataset.stat !== 'all') state.status = t.dataset.stat; update(); }
    else if (t.dataset.chip) { state.status = t.dataset.chip; update(); }
    else if (t.dataset.check) { state.check = state.check === t.dataset.check ? 'all' : t.dataset.check; update(); document.getElementById('results').scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }
    else if (t.dataset.view) { state.view = t.dataset.view; update(); }
    else if (t.dataset.toggle) { expanded[t.dataset.toggle] = !expanded[t.dataset.toggle]; update(); }
    else if (t.dataset.reset) { reset(); update(); }
  });
  root.addEventListener('input', function (e) {
    if (e.target.id === 'd-q') { state.q = e.target.value; update(); }
  });
  root.addEventListener('change', function (e) {
    var id = e.target.id;
    if (id === 'd-source') state.source = e.target.value;
    else if (id === 'd-check') state.check = e.target.value;
    else if (id === 'd-sort') state.sort = e.target.value;
    else return;
    update();
  });

  fetch('/api/dashboard').then(function (r) { if (!r.ok) throw new Error(); return r.json(); }).then(function (d) {
    data = d;
    build();
  }).catch(function () {
    root.innerHTML = '<div class="callout bad"><h2>Could not load the dashboard</h2><p>Refresh the page to try again.</p></div>';
  });
})();
