'use strict';

window.SehatiAuthenticator = function ({ request, enterWorkspace, showLogin, session, refreshAccount }) {
  const $ = id => document.getElementById(id);
  const message = (id, text = '') => { $(id).textContent = text; $(id).hidden = !text; };
  let pendingToken = '', recoveryLogin = false, recoveryCodes = [], resultSession = null, owner = '';
  let expiryTimer = null, epoch = 0, initialSetup = true;
  // Kept only in this closure for the second step, never in browser storage/URLs.
  let codeStep = false, loginPassword = '', loginUser = '', loginTimer = null;
  // A provisioning fragment is removed before any request, and never stored in web storage.
  const fragment = new URLSearchParams(location.hash.slice(1));
  let activation = fragment.get('activate') || '';
  let activationUser = fragment.get('user') || '';
  if (activation) history.replaceState(null, '', location.pathname + location.search);

  function clearQR() {
    if (expiryTimer) clearTimeout(expiryTimer);
    expiryTimer = null;
    $('mfa-qr').removeAttribute('src'); $('mfa-setup-key').textContent = '';
    $('mfa-confirm-code').value = ''; $('mfa-scan-panel').hidden = true;
  }
  function abandonPending() {
    const token = pendingToken; pendingToken = '';
    if (token) request('/api/auth/authenticator/cancel', { method: 'POST', json: { token } }).catch(() => {});
    clearQR();
  }
  function setRecoveryLogin(value) {
    recoveryLogin = value;
    $('totp-field').hidden = !codeStep || value; $('totp').disabled = !codeStep || value; $('totp').required = codeStep && !value;
    $('recovery-field').hidden = !codeStep || !value; $('recovery-code').disabled = !codeStep || !value; $('recovery-code').required = codeStep && value;
    $('use-recovery').textContent = value ? 'Gunakan kode Google Authenticator' : 'Gunakan kode pemulihan';
    if (codeStep) {
      $('login-title').textContent = value ? 'Gunakan kode pemulihan.' : 'Buka Google Authenticator.';
      $('login-description').textContent = value
        ? 'Masukkan salah satu kode pemulihan yang Anda simpan saat memasangkan HP.'
        : 'Masukkan kode 6 digit yang muncul pada entri Sehati di HP Anda.';
    }
    $('totp').value = ''; $('recovery-code').value = ''; message('login-error');
  }
  function reset() {
    epoch += 1;
    if (loginTimer) clearTimeout(loginTimer);
    loginTimer = null; loginPassword = ''; loginUser = ''; codeStep = false;
    $('password').value = ''; $('username').disabled = false; $('password').disabled = false;
    $('credentials-fields').hidden = false; $('login-account-name').hidden = true;
    $('login-account-name').textContent = ''; $('login-back').hidden = true; $('use-recovery').hidden = true;
    $('login-submit-label').textContent = 'Lanjutkan'; $('login-submit').disabled = false;
    abandonPending(); recoveryCodes = []; resultSession = null; owner = '';
    $('mfa-recovery-list').replaceChildren(); $('mfa-recovery-dialog').close(); $('mfa-codes-saved').checked = false;
    $('mfa-finish').disabled = true;
    $('mfa-start-form').reset(); $('mfa-confirm-form').reset(); $('mfa-regenerate-form').reset();
    setSetupMode('initial');
    $('normal-login').hidden = false; $('authenticator-panel').hidden = true; $('mfa-start-form').hidden = false;
    $('login-title').textContent = 'Masuk ke akun Sehati.';
    $('login-description').textContent = 'Mulai dengan nama pengguna dan kata sandi. Jika ini pertama kali, kami bantu pasangkan Google Authenticator setelahnya.';
    setProgress(1);
    setRecoveryLogin(false);
  }
  function setProgress(step) {
    $('auth-step-account').removeAttribute('aria-current'); $('auth-step-phone').removeAttribute('aria-current');
    $(step === 1 ? 'auth-step-account' : 'auth-step-phone').setAttribute('aria-current', 'step');
  }
  function open(username = '', kind = 'initial', code = '') {
    reset();
    $('workspace').hidden = true; $('boot').hidden = true; $('login').hidden = false;
    $('normal-login').hidden = true; $('authenticator-panel').hidden = false;
    $('login-description').textContent = 'Kode login di HP Anda. Tanpa email atau terminal.';
    $('mfa-username').value = username; setSetupMode(kind); $('mfa-proof').value = code;
    message('mfa-error'); message('mfa-confirm-error');
    $('password').value = ''; $('totp').value = '';
    (username ? $('mfa-password') : $('mfa-username')).focus();
  }
  function setSetupMode(kind) {
    initialSetup = kind === 'initial';
    $('login-title').textContent = initialSetup ? 'Pasang Google Authenticator.' : 'Ganti authenticator Anda.';
    $('mfa-setup-intro').textContent = initialSetup
      ? 'Masukkan akun Sehati Anda untuk menampilkan QR. Setelah itu, pindai dengan Google Authenticator di HP. Tidak perlu email atau kode aktivasi.'
      : 'Gunakan kata sandi dan kode dari aplikasi lama atau kode pemulihan untuk memasangkan HP pengganti.';
    $('mfa-proof-fields').hidden = initialSetup;
    $('mfa-proof-kind').disabled = initialSetup;
    $('mfa-proof-kind').value = initialSetup ? 'totp' : kind;
    $('mfa-proof').disabled = initialSetup; $('mfa-proof').required = !initialSetup; $('mfa-proof').value = '';
    $('mfa-change-mode').textContent = initialSetup ? 'Sudah pernah memasang? Ganti HP' : 'Kembali ke pemasangan pertama';
    updateProof();
  }
  function updateProof() {
    const isTotp = $('mfa-proof-kind').value === 'totp';
    $('mfa-proof').inputMode = isTotp ? 'numeric' : 'text';
    $('mfa-proof').placeholder = isTotp ? 'Kode 6 digit yang belum dipakai' : 'Tempel kode pribadi Anda';
    if (isTotp) $('mfa-proof').pattern = '[0-9]{6}'; else $('mfa-proof').removeAttribute('pattern');
  }
  function showQR(data, startedInitial) {
    pendingToken = data.token; owner = data.username;
    $('mfa-password').value = ''; $('mfa-proof').value = ''; $('password').value = '';
    $('login-title').textContent = 'Pindai QR dengan HP Anda.';
    $('login-description').textContent = 'Buka Google Authenticator untuk memasangkan akun Sehati. Tidak perlu email atau kode dari terminal.';
    setProgress(2);
    $('mfa-entry-name').textContent = `Sehati — ${data.username}`; $('mfa-manual-name').textContent = data.username;
    $('mfa-setup-key').textContent = data.setup_key; $('mfa-qr').src = data.qr_image;
    $('mfa-start-form').hidden = true; $('mfa-scan-panel').hidden = false;
    expiryTimer = setTimeout(() => {
      if (startedInitial) showLogin('QR sudah kedaluwarsa. Masukkan nama pengguna dan kata sandi lagi untuk melanjutkan pemasangan.');
      else {
        abandonPending(); $('mfa-start-form').hidden = false; setProgress(1);
        message('mfa-error', 'QR sudah kedaluwarsa. Mulai kembali dengan kode aplikasi atau kode pemulihan yang baru.');
      }
    }, Math.max(0, new Date(data.expires_at).getTime() - Date.now()));
    $('mfa-confirm-code').focus();
  }
  function showCodeStep(username, password) {
    codeStep = true; loginUser = username; loginPassword = password;
    $('password').value = ''; $('username').disabled = true; $('password').disabled = true;
    $('credentials-fields').hidden = true;
    $('login-title').textContent = 'Buka Google Authenticator.';
    $('login-description').textContent = 'Masukkan kode 6 digit yang muncul pada entri Sehati di HP Anda.';
    $('login-account-name').textContent = `Akun: ${username}`; $('login-account-name').hidden = false;
    $('login-submit-label').textContent = 'Masuk ke ruang staf';
    $('login-back').hidden = false; $('use-recovery').hidden = false;
    setProgress(2); setRecoveryLogin(false); $('totp').focus();
    loginTimer = setTimeout(() => showLogin('Waktu verifikasi habis. Masukkan nama pengguna dan kata sandi lagi.'), 5 * 60 * 1000);
  }
  $('login-form').addEventListener('submit', async event => {
    event.preventDefault(); message('login-error'); $('login-submit').disabled = true;
    const currentEpoch = epoch;
    try {
      if (codeStep) {
        const data = await request('/api/auth/login', {method:'POST', json:{
          username:loginUser, password:loginPassword,
          ...(recoveryLogin ? {recovery_code:$('recovery-code').value.trim()} : {totp:$('totp').value.trim()})
        }});
        if (currentEpoch !== epoch) return;
        loginPassword = ''; await enterWorkspace(data);
      } else {
        const password = $('password').value;
        const data = await request('/api/auth/authenticator/next', {method:'POST', json:{
          username:$('username').value.trim(), password
        }});
        if (currentEpoch !== epoch) {
          if (data.token) request('/api/auth/authenticator/cancel', {method:'POST',json:{token:data.token}}).catch(() => {});
          return;
        }
        $('password').value = '';
        if (data.step === 'setup') { open(data.username); showQR(data, true); }
        else if (data.step === 'code') showCodeStep(data.username, password);
        else throw new Error('Langkah login tidak dikenali. Muat ulang halaman.');
      }
    } catch (error) {
      if (currentEpoch === epoch) message('login-error', !codeStep && error.status === 401
        ? 'Nama pengguna atau kata sandi tidak cocok. Silakan periksa kembali.' : error.message);
    }
    finally {
      if (currentEpoch === epoch) {
        $('login-submit').disabled = false; $('password').value = ''; $('totp').value = ''; $('recovery-code').value = '';
      }
    }
  });
  function showCodes(codes, username, nextSession = null) {
    recoveryCodes = codes; owner = username; resultSession = nextSession;
    $('mfa-recovery-list').replaceChildren(...codes.map(value => {
      const code = document.createElement('code'); code.textContent = value; return code;
    }));
    $('mfa-codes-saved').checked = false; $('mfa-finish').disabled = true; message('mfa-finish-error');
    $('mfa-recovery-dialog').showModal();
  }
  $('use-recovery').addEventListener('click', () => setRecoveryLogin(!recoveryLogin));
  $('open-authenticator').addEventListener('click', () => open(loginUser || $('username').value.trim(), 'totp'));
  $('login-back').addEventListener('click', () => { showLogin(); $('username').focus(); });
  $('account-setup-mfa').addEventListener('click', () => open(session()?.user.username || '', 'totp'));
  $('mfa-proof-kind').addEventListener('change', () => { $('mfa-proof').value = ''; updateProof(); });
  $('mfa-change-mode').addEventListener('click', () => { setSetupMode(initialSetup ? 'totp' : 'initial'); message('mfa-error'); });
  $('mfa-cancel').addEventListener('click', async () => {
    const previous = session(); reset();
    if (previous) { try { await enterWorkspace(previous); } catch (_) { showLogin(); } }
    else showLogin();
  });
  $('mfa-start-form').addEventListener('submit', async event => {
    event.preventDefault(); message('mfa-error'); $('mfa-start').disabled = true;
    const currentEpoch = epoch, startedInitial = initialSetup;
    $('mfa-change-mode').disabled = true;
    try {
      const data = await request('/api/auth/authenticator/start', { method: 'POST', json: {
        username: $('mfa-username').value.trim(), password: $('mfa-password').value,
        ...(startedInitial ? {kind: 'initial'} : {kind: $('mfa-proof-kind').value, proof: $('mfa-proof').value.trim()})
      } });
      if (currentEpoch !== epoch) {
        request('/api/auth/authenticator/cancel', {method:'POST',json:{token:data.token}}).catch(() => {});
        return;
      }
      showQR(data, startedInitial);
    } catch (error) {
      if (currentEpoch === epoch) message('mfa-error', startedInitial && error.status === 401
        ? 'Akun atau kata sandi belum cocok, atau pemasangan pertama belum diizinkan. Periksa akun Anda; hubungi pengelola jika masih belum bisa.' : error.message);
    }
    finally { $('mfa-start').disabled = false; $('mfa-change-mode').disabled = false; }
  });
  $('mfa-confirm-form').addEventListener('submit', async event => {
    event.preventDefault(); message('mfa-confirm-error'); $('mfa-confirm').disabled = true;
    const currentEpoch = epoch; $('mfa-cancel').disabled = true;
    try {
      const data = await request('/api/auth/authenticator/confirm', { method: 'POST', json: {
        token: pendingToken, code: $('mfa-confirm-code').value.trim()
      } });
      if (currentEpoch !== epoch) return;
      pendingToken = ''; clearQR();
      const codes = data.recovery_codes; delete data.recovery_codes;
      showCodes(codes, owner, data);
    } catch (error) { if (currentEpoch === epoch) message('mfa-confirm-error', error.message); }
    finally { $('mfa-confirm-code').value = ''; $('mfa-confirm').disabled = false; $('mfa-cancel').disabled = false; }
  });
  $('mfa-regenerate-form').addEventListener('submit', async event => {
    event.preventDefault(); message('mfa-regen-error'); $('mfa-regenerate').disabled = true;
    const currentEpoch = epoch;
    try {
      const username = session().user.username;
      const data = await request('/api/auth/authenticator/recovery-codes', { method: 'POST', json: {
        username, password: $('mfa-regen-password').value, kind: 'totp', proof: $('mfa-regen-code').value.trim()
      } });
      if (currentEpoch !== epoch) return;
      $('mfa-regenerate-form').reset(); showCodes(data.recovery_codes, username);
    } catch (error) { if (currentEpoch === epoch) message('mfa-regen-error', error.message); }
    finally { $('mfa-regen-password').value = ''; $('mfa-regen-code').value = ''; $('mfa-regenerate').disabled = false; }
  });
  $('mfa-codes-saved').addEventListener('change', () => { $('mfa-finish').disabled = !$('mfa-codes-saved').checked; });
  $('mfa-recovery-dialog').addEventListener('cancel', event => event.preventDefault());
  $('mfa-download-codes').addEventListener('click', () => {
    const text = `SEHATI — KODE PEMULIHAN PRIBADI\nAkun: ${owner}\n\nSetiap kode hanya dapat dipakai sekali bersama kata sandi. Simpan di tempat pribadi, terpisah dari HP authenticator.\n\n${recoveryCodes.join('\n')}\n`;
    const url = URL.createObjectURL(new Blob([text], {type:'text/plain;charset=utf-8'}));
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'sehati-kode-pemulihan.txt'; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  $('mfa-finish').addEventListener('click', async () => {
    if (!$('mfa-codes-saved').checked) return;
    const next = resultSession; resultSession = null; recoveryCodes = [];
    $('mfa-recovery-list').replaceChildren(); $('mfa-recovery-dialog').close();
    try { if (next) await enterWorkspace(next); else await refreshAccount(); }
    catch (_) { showLogin('Authenticator sudah aktif. Silakan masuk menggunakan kode baru dari HP Anda.'); }
  });
  return {
    reset,
    hasActivation: () => Boolean(activation),
    openActivation: () => { const code = activation, username = activationUser; activation = ''; activationUser = ''; open(username, 'activation', code); }
  };
};
