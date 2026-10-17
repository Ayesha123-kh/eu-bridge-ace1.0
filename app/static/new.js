(function () {
  var form = document.getElementById('scan-form');
  var errorBox = document.getElementById('form-error');
  var scanning = document.getElementById('scanning');
  var backBtn = document.getElementById('back-btn');
  var nextBtn = document.getElementById('next-btn');
  var submitBtn = document.getElementById('submit-btn');
  var step = 1;
  var LAST = 3;
  var REPO_RE = /^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/?$/;

  function $(id) { return document.getElementById(id); }
  function radio(name) { var el = form.querySelector('input[name="' + name + '"]:checked'); return el ? el.value : ''; }
  function checks(name) { return Array.prototype.map.call(form.querySelectorAll('input[name="' + name + '"]:checked'), function (e) { return e.value; }); }
  function showError(msg) { errorBox.textContent = msg; errorBox.hidden = false; errorBox.scrollIntoView({ block: 'nearest' }); }
  function clearError() { errorBox.hidden = true; }

  function syncSource() {
    var vis = radio('visibility');
    var priv = vis === 'private';
    $('public-box').hidden = vis !== 'public';
    $('private-box').hidden = !priv;
    $('assess-box').hidden = vis !== 'assessment';
    var zip = radio('method') === 'zip';
    $('token-box').hidden = zip;
    $('zip-box').hidden = !zip;
  }
  form.addEventListener('change', function (e) {
    if (e.target.name === 'visibility' || e.target.name === 'method') syncSource();
  });

  function show(n) {
    step = n;
    Array.prototype.forEach.call(form.querySelectorAll('.step'), function (s) { s.hidden = Number(s.dataset.step) !== n; });
    Array.prototype.forEach.call(document.querySelectorAll('[data-dot]'), function (d) {
      var k = Number(d.dataset.dot);
      d.className = k === n ? 'on' : (k < n ? 'done' : '');
    });
    backBtn.hidden = n === 1;
    nextBtn.hidden = n === LAST;
    submitBtn.hidden = n !== LAST;
    submitBtn.textContent = radio('visibility') === 'assessment' ? 'Get assessment' : 'Scan code';
    clearError();
    window.scrollTo({ top: 0 });
  }

  function validate(n) {
    if (n === 1) {
      var vis = radio('visibility');
      if (vis === 'assessment') {
        return true;
      } else if (vis === 'public') {
        if (!REPO_RE.test($('repo_url').value.trim())) { showError('Enter a repository URL like https://github.com/owner/repository.'); $('repo_url').focus(); return false; }
      } else if (radio('method') === 'token') {
        if (!REPO_RE.test($('private_url').value.trim())) { showError('Enter the private repository URL, like https://github.com/your-company/repository.'); $('private_url').focus(); return false; }
        if (!$('access_token').value.trim()) { showError('Paste an access token that can read this repository.'); $('access_token').focus(); return false; }
      } else {
        var f = $('zip_file').files[0];
        if (!f) { showError('Choose a ZIP file of your source code.'); $('zip_file').focus(); return false; }
        if (f.size > 8 * 1024 * 1024) { showError('That ZIP is larger than 8 MB. Upload only the source code.'); return false; }
      }
    }
    if (n === 2 && !$('description').value.trim()) {
      showError('Describe what the product does in a sentence.');
      $('description').focus();
      return false;
    }
    return true;
  }

  nextBtn.addEventListener('click', function () { if (validate(step)) show(step + 1); });
  backBtn.addEventListener('click', function () { show(step - 1); });

  $('use-demo').addEventListener('click', function (e) {
    e.preventDefault();
    $('repo_url').value = 'https://github.com/Ayesha123-kh/eu-bridge-demo-chatbot';
    $('product_name').value = 'HireBot';
    $('description').value = 'An AI assistant that screens job applicants’ CVs';
    form.querySelector('input[name="user_groups"][value="job_applicants"]').checked = true;
    $('domain').value = 'hiring';
    form.querySelector('input[name="ai_features"][value="chat"]').checked = true;
    form.querySelector('input[name="ai_features"][value="decisions_about_people"]').checked = true;
    $('ai_provider').value = 'openai';
    form.querySelector('input[name="data_types"][value="contact"]').checked = true;
    form.querySelector('input[name="human_review"][value="sometimes"]').checked = true;
    $('repo_url').focus();
  });

  function errorText(body, status) {
    if (body && body.error) return body.error;
    if (body && typeof body.detail === 'string') return body.detail;
    if (body && Array.isArray(body.detail)) {
      return body.detail.map(function (d) {
        return (d.loc || []).slice(-1)[0] + ': ' + String(d.msg || '').replace('Value error, ', '');
      }).join('; ');
    }
    return 'Something went wrong (' + status + '). Please try again.';
  }

  function questionnaire() {
    var features = checks('ai_features');
    var data = checks('data_types');
    var provider = $('ai_provider').value;
    var usesLlm = features.indexOf('chat') !== -1 || features.indexOf('text_generation') !== -1 ||
      ['openai', 'anthropic', 'google', 'groq'].indexOf(provider) !== -1;
    return {
      product_name: $('product_name').value.trim(),
      description: $('description').value.trim(),
      user_groups: checks('user_groups'),
      eu_users: radio('eu_users'),
      uses_llm: usesLlm,
      processes_personal_data: data.length > 0,
      domain: $('domain').value,
      ai_features: features,
      data_types: data,
      ai_provider: provider,
      human_review: radio('human_review')
    };
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    clearError();
    if (!validate(1) || !validate(2)) return;
    var q = questionnaire();
    var vis = radio('visibility');
    var priv = vis === 'private';
    var zip = priv && radio('method') === 'zip';
    var req, label;

    if (vis === 'assessment') {
      req = fetch('/api/assessments', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(q) });
      label = 'your answers';
      $('scanning-text').textContent = 'Preparing your checklist from your answers. No code is read.';
    } else if (zip) {
      var file = $('zip_file').files[0];
      var fd = new FormData();
      fd.append('questionnaire', JSON.stringify(q));
      fd.append('file', file);
      req = fetch('/api/scans/upload', { method: 'POST', body: fd });
      label = file.name;
    } else {
      var url = (priv ? $('private_url') : $('repo_url')).value.trim();
      var payload = { source: priv ? 'private_token' : 'public', repo_url: url, questionnaire: q };
      if (priv) payload.access_token = $('access_token').value.trim();
      req = fetch('/api/scans', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      label = url.replace('https://github.com/', '');
    }

    $('scanning-repo').textContent = label;
    if (vis !== 'assessment') $('scanning-text').textContent = 'The AI is reviewing the code. This usually takes 20 to 60 seconds. Keep this page open.';
    form.hidden = true;
    document.querySelector('.steps').hidden = true;
    scanning.hidden = false;

    req.then(function (r) {
      return r.json().catch(function () { return null; }).then(function (body) {
        if (!r.ok) throw new Error(errorText(body, r.status));
        $('access_token').value = '';
        window.location.href = '/scans/' + body.scan_id;
      });
    }).catch(function (err) {
      scanning.hidden = true;
      form.hidden = false;
      document.querySelector('.steps').hidden = false;
      showError(err.message || 'Could not reach the server. Please try again.');
    });
  });

  syncSource();
  show(1);
})();
