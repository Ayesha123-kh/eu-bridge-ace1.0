(function () {
  var form = document.getElementById('auth-form');
  var err = document.getElementById('auth-error');
  var mode = form.dataset.mode;

  function setMode(m) {
    mode = m;
    document.getElementById('name-field').hidden = m === 'signin';
    document.getElementById('pw-hint').hidden = m === 'signin';
    document.getElementById('tab-signin').setAttribute('aria-selected', String(m === 'signin'));
    document.getElementById('tab-signup').setAttribute('aria-selected', String(m === 'signup'));
    document.getElementById('auth-submit').textContent = m === 'signin' ? 'Sign in' : 'Create account';
    document.getElementById('password').autocomplete = m === 'signin' ? 'current-password' : 'new-password';
    err.hidden = true;
  }
  document.getElementById('tab-signin').addEventListener('click', function () { setMode('signin'); });
  document.getElementById('tab-signup').addEventListener('click', function () { setMode('signup'); });

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    err.hidden = true;
    var body = { email: document.getElementById('email').value.trim(), password: document.getElementById('password').value };
    if (mode === 'signup') body.name = document.getElementById('name').value.trim();
    if (!body.email || !body.password || (mode === 'signup' && !body.name)) {
      err.textContent = 'Fill in every field.';
      err.hidden = false;
      return;
    }
    var btn = document.getElementById('auth-submit');
    btn.disabled = true;
    fetch('/api/auth/' + (mode === 'signup' ? 'signup' : 'login'), {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
    }).then(function (r) {
      return r.json().catch(function () { return null; }).then(function (data) {
        if (!r.ok) throw new Error((data && typeof data.detail === 'string') ? data.detail : 'Something went wrong. Please try again.');
        window.location.href = form.dataset.next || '/';
      });
    }).catch(function (e2) {
      err.textContent = e2.message;
      err.hidden = false;
      btn.disabled = false;
    });
  });
})();
