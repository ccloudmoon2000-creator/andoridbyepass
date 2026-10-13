const $ = (id) => document.getElementById(id);
const statusPill = $('status-pill');
const notice = $('notice');
const overlay = $('empty-overlay');
let lastStatus = null;
let requestInFlight = false;

async function api(path, method = 'GET', payload = undefined) {
  const options = { method, headers: { 'Accept': 'application/json' } };
  if (payload !== undefined) {
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(payload);
  }
  const res = await fetch(path, options);
  let body = {};
  try { body = await res.json(); } catch (_) { /* return an HTTP-specific message below */ }
  if (!res.ok) throw new Error(body.detail || `Pedido falhou (HTTP ${res.status})`);
  return body;
}

function setNotice(message, isError = false) {
  notice.textContent = message;
  notice.classList.toggle('error', isError);
}

function statusLabel(s) {
  if (!s.image_ready) return 'Imagem em falta';
  if (s.android_state === 'booted') return 'Android iniciado';
  if (s.android_state === 'starting') return 'A arrancar';
  return s.emulator_process_running ? 'A ligar' : 'Parado';
}

function renderStatus(s) {
  lastStatus = s;
  const state = !s.image_ready ? 'error' : s.android_state;
  statusPill.dataset.state = state === 'booted' ? 'booted' : (state === 'error' ? 'error' : 'checking');
  $('status-label').textContent = statusLabel(s);
  $('summary').textContent = s.android_state === 'booted'
    ? 'O dispositivo Android responde ao ADB.'
    : (s.image_ready ? (s.emulator_process_running ? 'O processo existe; a aguardar disponibilidade do Android.' : 'O emulador está parado.') : 'O serviço web está ativo, mas falta a imagem AOSP compilada.');
  $('version').textContent = s.android_version
    ? `Android ${s.android_version} · API ${s.android_sdk || '—'} · build ${s.build_id || '—'}`
    : `Versão Android por confirmar · alvo esperado: Android ${s.expected_android_version}`;
  $('diagnostics').textContent = JSON.stringify(s, null, 2);
  overlay.classList.toggle('visible', !s.emulator_process_running && !s.image_ready);
  if (s.android_state === 'booted') setNotice('Ligação ao Android confirmada por ADB. A transmissão do ecrã é feita pelo noVNC.');
  else if (!s.image_ready) setNotice('Para arrancar o sistema verdadeiro, compile o alvo AOSP Android 12 e coloque os artefactos na pasta aosp-image.', true);
  else if (s.emulator_process_running) setNotice('O processo do emulador está ativo. A primeira inicialização pode demorar.');
  else setNotice('O emulador ainda não está em execução. Utilize “Iniciar” depois de montar a imagem.');
}

async function refreshStatus() {
  try { renderStatus(await api('/api/status')); }
  catch (err) {
    statusPill.dataset.state = 'error';
    $('status-label').textContent = 'Serviço indisponível';
    $('summary').textContent = 'Não foi possível consultar o backend remoto.';
    setNotice(err.message, true);
    $('diagnostics').textContent = err.stack || err.message;
  }
}

async function action(path, message, payload) {
  if (requestInFlight) return;
  requestInFlight = true;
  const buttons = [...document.querySelectorAll('button')];
  buttons.forEach((b) => { b.disabled = true; });
  setNotice(message);
  try {
    const result = await api(path, 'POST', payload);
    setNotice(result.message || 'Comando enviado ao Android.');
    await refreshStatus();
  } catch (err) {
    setNotice(err.message, true);
  } finally {
    buttons.forEach((b) => { b.disabled = false; });
    requestInFlight = false;
  }
}

$('start-btn').addEventListener('click', () => action('/api/start', 'A iniciar o emulador…'));
$('reboot-btn').addEventListener('click', () => action('/api/reboot', 'A enviar o reinício ao Android…'));
$('restart-btn').addEventListener('click', () => action('/api/restart', 'A reiniciar o processo do emulador…'));
$('stop-btn').addEventListener('click', () => action('/api/stop', 'A parar o processo do emulador…'));
document.querySelectorAll('[data-key]').forEach((button) => {
  button.addEventListener('click', () => action('/api/input/key', `A enviar a tecla ${button.dataset.key}…`, { key: button.dataset.key }));
});

// noVNC can occasionally take several seconds to initialize in a fresh container.
refreshStatus();
setInterval(refreshStatus, 4000);
