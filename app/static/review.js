(function () {
  var app = document.getElementById('app');
  var scanId = app.dataset.scanId;
  var data = null;
  var openForm = null; // {kind: 'finding'|'risk', id, mode}
  var busy = false;

  var RULES = {
    'AIA-50-1': { name: 'AI disclosure', law: 'EU AI Act, Art. 50(1)' },
    'GDPR-13': { name: 'Third-party AI notice', law: 'GDPR, Art. 13' },
    'GDPR-5-1C': { name: 'Personal data in logs', law: 'GDPR, Art. 5(1)(c)' }
  };
  var RISK = {
    minimal: 'Minimal risk',
    limited: 'Limited risk (AI transparency rules apply)',
    possibly_high: 'Possibly high-risk (EU AI Act, Annex III)',
    possibly_prohibited: 'Possibly prohibited'
  };

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function savedName() { try { return localStorage.getItem('eub_reviewer') || ''; } catch (e) { return ''; } }
  function saveName(v) { try { localStorage.setItem('eub_reviewer', v); } catch (e) { /* ignore */ } }
  function fmt(iso) {
    if (!iso) return '';
    var d = new Date(iso);
    if (isNaN(d)) return iso;
    return d.toLocaleString(undefined, { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  }
  function errorText(b, status) {
    if (b && b.error) return b.error;
    if (b && typeof b.detail === 'string') return b.detail;
    if (b && Array.isArray(b.detail)) {
      return b.detail.map(function (d) {
        return (d.loc || []).slice(-1)[0] + ': ' + String(d.msg || '').replace('Value error, ', '');
      }).join('; ');
    }
    return 'Something went wrong (' + status + ').';
  }
  function api(path, opts) {
    return fetch(path, opts).then(function (r) {
      return r.json().catch(function () { return null; }).then(function (body) {
        if (!r.ok) throw new Error(errorText(body, r.status));
        return body;
      });
    });
  }
  function post(path, body) {
    return api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
  }

  /* ---------- diff ---------- */
  function diffLines(before, after) {
    var a = before.split('\n'), b = after.split('\n'), s = 0;
    while (s < a.length && s < b.length && a[s] === b[s]) s++;
    var ea = a.length, eb = b.length;
    while (ea > s && eb > s && a[ea - 1] === b[eb - 1]) { ea--; eb--; }
    return { top: a.slice(0, s), del: a.slice(s, ea), add: b.slice(s, eb), bot: a.slice(ea) };
  }
  function markChange(o, n) {
    var p = 0;
    while (p < o.length && p < n.length && o[p] === n[p]) p++;
    var q = 0;
    while (q < o.length - p && q < n.length - p && o[o.length - 1 - q] === n[n.length - 1 - q]) q++;
    function wrap(l) {
      var mid = l.slice(p, l.length - q);
      return esc(l.slice(0, p)) + (mid ? '<mark>' + esc(mid) + '</mark>' : '') + esc(l.slice(l.length - q));
    }
    return [wrap(o), wrap(n)];
  }
  function row(cls, sym, html) {
    return '<div class="dl ' + cls + '"><span class="sym">' + sym + '</span><code>' + (html || '&nbsp;') + '</code></div>';
  }
  function renderDiff(before, after) {
    var d = diffLines(before, after), out = '';
    d.top.slice(-2).forEach(function (l) { out += row('ctx', '&nbsp;', esc(l)); });
    if (d.del.length === 1 && d.add.length === 1) {
      var m = markChange(d.del[0], d.add[0]);
      out += row('del', '−', m[0]) + row('add', '+', m[1]);
    } else {
      d.del.forEach(function (l) { out += row('del', '−', esc(l)); });
      d.add.forEach(function (l) { out += row('add', '+', esc(l)); });
    }
    d.bot.slice(0, 2).forEach(function (l) { out += row('ctx', '&nbsp;', esc(l)); });
    return '<div class="diff" tabindex="0" role="group" aria-label="Proposed change">' + out + '</div>';
  }

  /* ---------- pieces ---------- */
  var DECIDED = ['approved', 'rejected', 'applied', 'apply_failed'];
  function isDecided(f) { return DECIDED.indexOf(f.status) !== -1; }
  function locked() { return data.scan.status === 'pr_opened'; }

  function statusPill(f) {
    var map = {
      pending: ['waiting', 'Needs your decision'],
      needs_human: ['waiting', 'Needs your decision'],
      approved: ['approved', f.final_patch ? 'Edited and approved' : 'Approved'],
      rejected: ['rejected', 'Rejected'],
      applied: ['applied', 'Applied in pull request'],
      apply_failed: ['failed', 'Approved, but could not be applied']
    };
    var m = map[f.status] || ['waiting', f.status];
    return '<span class="pill ' + m[0] + '">' + m[1] + '</span>';
  }

  function decisionForm(f) {
    var mode = openForm.mode;
    var titles = { approve: 'Approve this fix', edit: 'Edit the fix, then approve', reject: 'Reject this fix' };
    var label = { approve: 'Approve fix', edit: 'Approve edited fix', reject: 'Reject fix' }[mode];
    var patch = f.final_patch || f.suggested_patch;
    var h = '<form class="decision-form" data-form="finding" data-id="' + f.id + '" data-mode="' + mode + '" novalidate>';
    h += '<strong>' + titles[mode] + '</strong>';
    if (mode === 'edit') {
      h += '<div class="field" style="margin:0"><label for="patch-' + f.id + '">' + (data.scan.source === 'assessment' ? 'Edit the wording or code.' : 'Replacement code. It replaces the lines shown in red.') + '</label>' +
        '<textarea class="patch" id="patch-' + f.id + '" rows="5" spellcheck="false">' + esc(patch) + '</textarea></div>';
    }
    h += '<div class="row"><div class="field" style="margin:0"><label for="name-' + f.id + '">Your name</label>' +
      '<input type="text" id="name-' + f.id + '" value="' + esc(savedName()) + '" autocomplete="name" maxlength="80"></div>' +
      '<div class="field" style="margin:0"><label for="reason-' + f.id + '">Reason, in one line</label>' +
      '<input type="text" id="reason-' + f.id + '" maxlength="300" placeholder="' +
      (mode === 'reject' ? 'Why should this change not be made?' : 'Why is this change correct?') + '"></div></div>';
    h += '<p class="error" data-error hidden role="alert"></p>';
    h += '<div class="buttons"><button class="btn ' + (mode === 'reject' ? 'danger' : 'primary') + '" type="submit">' + label + '</button>' +
      '<button class="btn" type="button" data-act="cancel">Cancel</button></div></form>';
    return h;
  }

  function findingCard(f) {
    var rule = RULES[f.rule_id] || { name: f.title, law: f.rule_id === 'AIA-RISK' ? 'EU AI Act, Annex III' : '' };
    var after = f.final_patch || f.suggested_patch;
    var conf = Math.round((f.confidence || 0) * 100);
    var assess = data.scan.source === 'assessment';
    var h = '<article class="card" id="f-' + f.id + '">';
    h += '<div class="card-head"><span class="rule">' + esc(f.rule_id) + '</span><h3>' + esc(f.title || rule.name) + '</h3></div>';
    h += '<div class="facts"><span>' + esc(rule.law) + '</span>' +
      '<span>Severity: <span class="sev-' + esc(f.severity) + '">' + esc(f.severity) + '</span></span>' +
      (assess ? '<span>Recommended from your answers</span>' :
        '<span class="conf">AI confidence ' + conf + '%<span class="bar-track" aria-hidden="true"><span class="bar-fill" style="width:' + conf + '%;display:block"></span></span></span>') + '</div>';
    h += '<p class="explain">' + esc(f.explanation) + '</p>';
    if (f.status === 'needs_human' && f.needs_human_reason) {
      h += '<div class="flag"><strong>The AI was unsure.</strong> ' + esc(f.needs_human_reason) + ' Review this one carefully before deciding.</div>';
    }
    if (assess) {
      h += '<div class="diff-wrap"><div class="diff-title">Suggested wording or code' + (f.final_patch ? ' (edited by reviewer)' : '') + '</div><pre class="suggest">' + esc(after) + '</pre></div>';
    } else {
      h += '<div class="diff-wrap"><div class="diff-title">Proposed change' + (f.final_patch ? ' (edited by reviewer)' : '') + '</div>' +
        '<div class="file">' + esc(f.file_path) + '</div>' + renderDiff(f.original_snippet, after) +
        '<div class="diff-key">Red lines are removed. Green lines are added.</div></div>';
    }

    if (isDecided(f)) {
      h += '<div class="decided">' + statusPill(f) +
        '<span class="who">' + esc(f.reviewer) + '</span><span class="reason">“' + esc(f.review_reason) + '”</span>';
      if (!locked() && f.status !== 'applied') h += '<button class="linkbtn" type="button" data-act="change" data-id="' + f.id + '">Change decision</button>';
      h += '</div>';
    } else if (openForm && openForm.kind === 'finding' && openForm.id === f.id) {
      h += decisionForm(f);
    } else {
      h += '<div class="actions">' +
        '<button class="btn primary" type="button" data-act="approve" data-id="' + f.id + '">Approve</button>' +
        '<button class="btn" type="button" data-act="edit" data-id="' + f.id + '">Edit, then approve</button>' +
        '<button class="btn danger" type="button" data-act="reject" data-id="' + f.id + '">Reject</button></div>';
    }
    return h + '</article>';
  }

  function checksSummary() {
    var s = data.scan, h = '<section class="checks-summary"><h2>The four checks</h2>';
    Object.keys(RULES).forEach(function (rule) {
      var fs = data.findings.filter(function (f) { return f.rule_id === rule; });
      var state, cls;
      if (!fs.length) { state = s.source === 'assessment' ? 'Not recommended for your answers' : 'No issue found in the files reviewed'; cls = 'clear'; }
      else {
        var applied = fs.filter(function (f) { return f.status === 'applied'; }).length;
        var appr = fs.filter(function (f) { return f.status === 'approved' || f.status === 'applied'; }).length;
        var rej = fs.filter(function (f) { return f.status === 'rejected'; }).length;
        var wait = fs.filter(function (f) { return f.status === 'pending' || f.status === 'needs_human'; }).length;
        if (wait) { state = wait + ' waiting for your decision'; cls = 'open'; }
        else if (applied) { state = 'Fix sent in pull request'; cls = 'done'; }
        else if (appr) { state = s.source === 'assessment' ? 'Recommendation accepted' : 'Fix approved, ready to send'; cls = 'done'; }
        else if (rej) { state = s.source === 'assessment' ? 'Recommendation rejected' : 'Fix rejected'; cls = 'muted'; }
        else { state = 'Issue found'; cls = 'open'; }
      }
      h += '<div class="cs-row"><div><div class="name">' + esc(RULES[rule].name) + '</div><div class="law">' + esc(rule) + ' \u00b7 ' + esc(RULES[rule].law) + '</div></div><div class="state ' + cls + '">' + esc(state) + '</div></div>';
    });
    var rs, rc;
    if (s.status === 'escalated' || s.escalation_reason) {
      if (s.risk_reviewed_by) { rs = 'Escalated, confirmed by ' + s.risk_reviewed_by; rc = 'done'; }
      else { rs = 'Escalated, needs a person to confirm'; rc = 'open'; }
    } else { rs = 'No escalation needed'; rc = 'clear'; }
    h += '<div class="cs-row"><div><div class="name">Risk tier</div><div class="law">AIA-RISK \u00b7 EU AI Act, Annex III</div></div><div class="state ' + rc + '">' + esc(rs) + '</div></div>';
    return h + '</section>';
  }

  function riskPanel() {
    var s = data.scan;
    if (s.status !== 'escalated' && !s.escalation_reason) return '';
    if (s.risk_reviewed_by) {
      return '<div class="callout ok"><h2>Risk tier reviewed</h2><p>' + esc(s.escalation_reason) + '</p>' +
        '<p><strong>' + esc(s.risk_reviewed_by) + '</strong> confirmed on ' + esc(fmt(s.risk_reviewed_at)) + ': “' + esc(s.risk_reviewed_reason) + '”</p></div>';
    }
    var h = '<div class="callout warn"><h2>Escalated: a human or legal reviewer must confirm the risk tier before launch</h2>' +
      '<p>' + esc(s.escalation_reason) + '</p><p>The AI does not decide the risk tier for this product. The fixes below are still useful, but they do not make it compliant on their own.</p>';
    if (openForm && openForm.kind === 'risk') {
      h += '<form class="risk-form" data-form="risk" novalidate>' +
        '<div class="field" style="margin:0"><label for="risk-name">Your name</label><input type="text" id="risk-name" value="' + esc(savedName()) + '" maxlength="80" autocomplete="name"></div>' +
        '<div class="field" style="margin:0"><label for="risk-reason">Reason, in one line</label><input type="text" id="risk-reason" maxlength="300" placeholder="For example: sent to legal for Annex III assessment"></div>' +
        '<p class="error" data-error hidden role="alert"></p>' +
        '<div class="buttons" style="display:flex;gap:10px"><button class="btn primary" type="submit">Confirm risk tier reviewed</button><button class="btn" type="button" data-act="cancel">Cancel</button></div></form>';
    } else {
      h += '<p style="margin-top:12px"><button class="btn primary" type="button" data-act="risk-open">I’ve reviewed the risk tier</button></p>';
    }
    return h + '</div>';
  }

  var needToken = false;

  function prPanel(c) {
    var s = data.scan, zip = s.source === 'private_zip', assess = s.source === 'assessment';
    if (assess) {
      var okA = c.pending === 0 && c.approved > 0;
      var mA = c.pending > 0 ? c.pending + (c.pending === 1 ? ' recommendation still needs' : ' recommendations still need') + ' a decision.' :
        c.approved === 0 ? 'Accept at least one recommendation to download the checklist.' :
        c.approved + (c.approved === 1 ? ' recommendation' : ' recommendations') + ' accepted. The checklist lists each one with who accepted it and why.';
      return '<section class="card pr"><h2>Download your checklist</h2><p class="status">' + esc(mA) + '</p><div>' +
        (okA ? '<a class="btn primary" href="/api/scans/' + esc(s.id) + '/checklist">Download checklist (Markdown)</a>' : '<button class="btn primary" type="button" disabled>Download checklist (Markdown)</button>') + '</div></section>';
    }
    if (s.status === 'pr_opened') {
      return '<section class="card pr"><h2>Pull request opened</h2><p class="status">The approved fixes are on a new branch of ' +
        esc(s.repo_owner + '/' + s.repo_name) + '. Review the diff on GitHub before merging.</p>' +
        '<p><a class="btn primary" href="' + esc(s.pr_url) + '" target="_blank" rel="noopener">Open pull request on GitHub</a></p>' +
        '<p><a href="/audit">See the audit log</a></p></section>';
    }
    var msg, ok = false;
    if (c.pending > 0) msg = c.pending + (c.pending === 1 ? ' finding still needs' : ' findings still need') + ' a decision before ' + (zip ? 'the fixes can be downloaded.' : 'a pull request can be created.');
    else if (c.approved === 0) msg = 'Approve at least one fix to ' + (zip ? 'download the fixed files.' : 'create a pull request.');
    else {
      ok = true;
      if (zip) msg = c.approved + (c.approved === 1 ? ' approved fix' : ' approved fixes') + ' will be applied to your uploaded files. You get a ZIP with the fixed files, a patch, and a list of who approved what.';
      else msg = c.approved + (c.approved === 1 ? ' approved fix' : ' approved fixes') + ' will be committed to a new branch of ' +
        s.repo_owner + '/' + s.repo_name + ' and opened as a pull request. The pull request lists who approved each one.';
      if (c.needs_human > 0) msg += ' ' + c.needs_human + ' flagged ' + (c.needs_human === 1 ? 'finding has' : 'findings have') + ' no decision and will be left out.';
    }
    var h = '<section class="card pr"><h2>' + (zip ? 'Download the fixes' : 'Create the pull request') + '</h2><p class="status">' + esc(msg) + '</p>';
    if (!zip && (s.source === 'private_token' || needToken)) {
      h += '<div class="tokenbox"><label for="pr-token">' + (s.source === 'private_token' ? 'Access token with write access to this repository' : 'The shared token cannot write to this repository. Paste a token that can') +
        '</label><input type="password" id="pr-token" autocomplete="off" spellcheck="false" placeholder="github_pat_\u2026"><p class="hint">Used once to open the pull request. It is never stored or logged.</p></div>';
    }
    h += '<p class="error" id="pr-error" hidden role="alert"></p>';
    if (zip && !s.has_files) h += '<p class="meta-note">Your uploaded files have been deleted from this server.</p>';
    else if (zip) h += '<div style="display:flex;gap:16px;align-items:center;flex-wrap:wrap">' + (ok ? '<a class="btn primary" href="/api/scans/' + esc(s.id) + '/patch" id="dl-link">Download fixed files (ZIP)</a>' : '<button class="btn primary" type="button" disabled>Download fixed files (ZIP)</button>') +
      '<button class="linkbtn danger-link" type="button" data-act="delete-files">Delete my uploaded code from this server</button></div>';
    else h += '<div><button class="btn primary" type="button" data-act="pr"' + (ok ? '' : ' disabled') + '>Create pull request</button></div>';
    return h + '</section>';
  }

  function render() {
    var s = data.scan, c = data.counts;
    if (s.status === 'failed') {
      app.innerHTML = '<div class="callout bad"><h2>The scan could not finish</h2><p>' + esc(s.error || 'Unknown error.') +
        '</p><p><a href="/">Start a new scan</a></p></div>';
      return;
    }
    var edited = c.edited, plain = c.approved - edited, waiting = c.pending + c.needs_human;
    var h = '<div class="scanhead"><h1>' + esc(s.source === 'assessment' ? s.repo_name : s.repo_owner + '/' + s.repo_name) + '</h1>' +
      '<p class="meta">' + (s.source === 'assessment' ? 'No-code assessment \u00b7 ' : s.source === 'private_zip' ? 'Uploaded ZIP ' + esc(s.source_name || '') + ' \u00b7 ' : s.source === 'private_token' ? 'Private repository \u00b7 ' : '') + 'Scanned ' + esc(fmt(s.created_at)) + (s.commit_sha ? ' · commit ' + esc(s.commit_sha.slice(0, 7)) : '') +
      (s.source === 'public' && (s.notes || {}).license ? ' \u00b7 Licence ' + esc(s.notes.license) : '') + ' \u00b7 Risk tier: <strong>' + esc(RISK[s.risk_tier] || s.risk_tier || 'unknown') + '</strong></p></div>';
    h += riskPanel() + checksSummary();
    var notes = s.notes || {};
    if (s.source === 'public' && s.notes && 'license' in notes && !notes.license) {
      h += '<div class="callout warn"><h2>This repository has no open-source licence</h2><p>You can scan it, but without a licence the owner keeps all rights. Do not open a pull request unless you own the code or have the owner\u2019s permission.</p></div>';
    }
    if (s.source !== 'assessment' && notes.files_scanned != null) {
      h += '<p class="meta-note">' + notes.files_scanned + ' ' + (notes.files_scanned === 1 ? 'file' : 'files') +
        ' with AI-related code reviewed.' + (notes.secrets_masked ? ' ' + notes.secrets_masked + ' ' + (notes.secrets_masked === 1 ? 'secret was' : 'secrets were') + ' masked before the code was sent to the AI.' : '') +
        (notes.warnings || []).map(function (w) { return ' ' + esc(w); }).join('') + '</p>';
    }
    h += '<p class="tally">' + (s.source === 'assessment' ? 'Recommended' : 'AI suggested') + ' <b>' + c.suggested + '</b><span class="sep">·</span>Approved <b>' + plain +
      '</b><span class="sep">·</span>Edited <b>' + edited + '</b><span class="sep">·</span>Rejected <b>' + c.rejected +
      '</b><span class="sep">·</span>Waiting for you <b>' + waiting + '</b></p>';

    if (!data.findings.length) {
      h += '<div class="callout"><h2>No issues found</h2><p>The AI found nothing to fix in the files it reviewed. This does not prove the product is compliant.</p></div>';
    } else {
      var todo = data.findings.filter(function (f) { return !isDecided(f); });
      var done = data.findings.filter(isDecided);
      h += '<div class="findings">';
      if (todo.length) h += '<div class="group-title">Waiting for your decision (' + todo.length + ')</div>' + todo.map(findingCard).join('');
      if (done.length) h += '<div class="group-title">Decided (' + done.length + ')</div>' + done.map(findingCard).join('');
      h += '</div>';
    }
    h += prPanel(c);
    app.innerHTML = h;
  }

  /* ---------- data + events ---------- */
  function load(keepForm) {
    return api('/api/scans/' + scanId).then(function (d) {
      data = d;
      if (!keepForm) openForm = null;
      render();
    }).catch(function (err) {
      app.innerHTML = '<div class="callout bad"><h2>Could not load this scan</h2><p>' + esc(err.message) + '</p><p><a href="/">Back to new scan</a></p></div>';
    });
  }

  function showFormError(form, msg) {
    var el = form.querySelector('[data-error]');
    el.textContent = msg;
    el.hidden = false;
  }

  app.addEventListener('click', function (e) {
    var t = e.target.closest('[data-act]');
    if (!t) return;
    var act = t.dataset.act, id = t.dataset.id;
    if (act === 'approve' || act === 'edit' || act === 'reject') {
      openForm = { kind: 'finding', id: id, mode: act };
      render();
      var el = document.getElementById('reason-' + id);
      if (el) el.focus();
    } else if (act === 'change') {
      data.findings.forEach(function (f) { if (f.id === id) { f.status = 'pending'; } });
      openForm = null;
      render();
    } else if (act === 'cancel') {
      openForm = null;
      load(false);
    } else if (act === 'risk-open') {
      openForm = { kind: 'risk' };
      render();
      document.getElementById('risk-reason').focus();
    } else if (act === 'delete-files') {
      if (busy) return;
      busy = true;
      api('/api/scans/' + scanId + '/files', { method: 'DELETE' }).then(function () { return load(true); }).finally(function () { busy = false; });
    } else if (act === 'pr') {
      if (busy) return;
      var tokenEl = document.getElementById('pr-token');
      var token = tokenEl ? tokenEl.value.trim() : '';
      var errBox = document.getElementById('pr-error');
      if (tokenEl && !token) {
        errBox.textContent = 'Enter an access token with write access to continue.';
        errBox.hidden = false;
        tokenEl.focus();
        return;
      }
      busy = true;
      t.disabled = true;
      t.textContent = 'Creating pull request\u2026';
      post('/api/scans/' + scanId + '/pr', token ? { access_token: token } : undefined).then(function () { return load(false); }).catch(function (err) {
        if (/GitHub returned (401|403|404)/.test(err.message)) needToken = true;
        load(true).then(function () {
          var b2 = document.getElementById('pr-error');
          if (b2) { b2.textContent = err.message; b2.hidden = false; }
        });
      }).finally(function () { busy = false; });
    }
  });

  app.addEventListener('submit', function (e) {
    e.preventDefault();
    var form = e.target;
    var kind = form.dataset.form;
    var name = form.querySelector('input[type="text"]').value.trim();
    var reasonEl = form.querySelectorAll('input[type="text"]')[form.querySelectorAll('input[type="text"]').length - 1];
    var reason = reasonEl.value.trim();
    if (!name) { showFormError(form, 'Enter your name so the decision can be attributed to you.'); return; }
    if (reason.length < 5) { showFormError(form, 'Give a reason of at least 5 characters.'); return; }
    saveName(name);
    var btn = form.querySelector('button[type="submit"]');
    btn.disabled = true;
    var req;
    if (kind === 'risk') {
      req = post('/api/scans/' + scanId + '/risk-review', { reviewer: name, reason: reason });
    } else {
      var mode = form.dataset.mode, id = form.dataset.id;
      var body = { action: mode === 'approve' ? 'approve' : mode === 'edit' ? 'edit_and_approve' : 'reject', reviewer: name, reason: reason };
      if (mode === 'edit') {
        var patch = form.querySelector('textarea').value;
        if (!patch.trim()) { btn.disabled = false; showFormError(form, 'The replacement code cannot be empty.'); return; }
        body.final_patch = patch;
      }
      req = post('/api/findings/' + id + '/review', body);
    }
    req.then(function () { return load(false); }).catch(function (err) {
      btn.disabled = false;
      showFormError(form, err.message);
    });
  });

  load(false);
})();
