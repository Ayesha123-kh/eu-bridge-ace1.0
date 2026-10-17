(function () {
  var form = document.getElementById('scan-form');
  var errorBox = document.getElementById('form-error');
  var scanning = document.getElementById('scanning');

  document.getElementById('use-demo').addEventListener('click', function (e) {
    e.preventDefault();
    form.repo_url.value = 'https://github.com/Ayesha123-kh/eu-bridge-demo-chatbot';
    form.description.value = 'An AI assistant that screens job applicants’ CVs';
    form.users.value = 'Job applicants and recruiters';
    form.domain.value = 'hiring';
    form.repo_url.focus();
  });

  function showError(msg) {
    errorBox.textContent = msg;
    errorBox.hidden = false;
  }

  function errorText(body, status) {
    if (body && body.error) return body.error;
    if (body && typeof body.detail === 'string') return body.detail;
    if (body && Array.isArray(body.detail)) {
      return body.detail.map(function (d) {
        var field = (d.loc || []).slice(-1)[0];
        return field + ': ' + String(d.msg || '').replace('Value error, ', '');
      }).join('; ');
    }
    return 'Something went wrong (' + status + '). Please try again.';
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    errorBox.hidden = true;
    var url = form.repo_url.value.trim();
    if (!/^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/?$/.test(url)) {
      showError('Enter a repository URL like https://github.com/owner/repository.');
      form.repo_url.focus();
      return;
    }
    if (!form.description.value.trim()) {
      showError('Describe what the product does in a sentence.');
      form.description.focus();
      return;
    }
    var payload = {
      repo_url: url,
      questionnaire: {
        description: form.description.value.trim(),
        users: form.users.value.trim(),
        uses_llm: form.uses_llm.value === 'yes',
        processes_personal_data: form.personal.value === 'yes',
        domain: form.domain.value
      }
    };
    document.getElementById('scanning-repo').textContent = url.replace('https://github.com/', '');
    form.hidden = true;
    scanning.hidden = false;

    fetch('/api/scans', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }).then(function (r) {
      return r.json().catch(function () { return null; }).then(function (body) {
        if (!r.ok) throw new Error(errorText(body, r.status));
        window.location.href = '/scans/' + body.scan_id;
      });
    }).catch(function (err) {
      scanning.hidden = true;
      form.hidden = false;
      showError(err.message || 'Could not reach the server. Please try again.');
    });
  });
})();
