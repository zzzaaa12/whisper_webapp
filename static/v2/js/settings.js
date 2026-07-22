const form = document.querySelector('[data-settings-form]');
const message = document.querySelector('[data-settings-message]');
const submit = form.querySelector('[type="submit"]');

function readValue(input) {
  if (input.type === 'checkbox') return input.checked;
  if (input.dataset.valueType === 'number') return Number(input.value);
  if (input.dataset.valueType === 'list') return input.value.split(',').map((item) => item.trim()).filter(Boolean);
  return input.value;
}

form.addEventListener('submit', async (event) => {
  event.preventDefault(); submit.disabled = true; message.textContent = '正在儲存…'; message.dataset.type = '';
  const values = {};
  form.querySelectorAll('[data-config-key]').forEach((input) => { values[input.dataset.configKey] = readValue(input); });
  try {
    const response = await fetch('/v2/settings', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({values})});
    const payload = await response.json();
    if (!response.ok || !payload.success) throw new Error(payload.message || '設定儲存失敗');
    message.textContent = payload.restart_required ? '設定已儲存，系統連線設定需要重新啟動後生效。' : '設定已儲存。';
    message.dataset.type = 'success'; window.v2Notify(message.textContent);
    form.querySelectorAll('input[type="password"]').forEach((input) => { input.value = ''; });
  } catch (error) { message.textContent = error.message; message.dataset.type = 'error'; window.v2Notify(error.message, 'error'); }
  finally { submit.disabled = false; }
});
