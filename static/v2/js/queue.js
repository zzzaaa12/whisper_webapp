import {api} from './api-client.js';

const list = document.querySelector('[data-queue-list]');
const message = document.querySelector('[data-queue-message]');
const template = document.querySelector('#queue-task-template');
const refreshButton = document.querySelector('[data-refresh-queue]');
let activeFilter = '';

const statusLabels = {queued: '等待中', processing: '處理中', completed: '已完成', failed: '失敗', cancelled: '已取消'};
const typeLabels = {youtube: '網址', upload_media: '本機檔案', upload_subtitle: '字幕檔案'};

function taskName(task) {
  return task.result?.video_title || task.data?.title || task.data?.display_name || task.data?.original_filename || task.data?.filename || '處理任務';
}
function formatTime(value) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return new Intl.DateTimeFormat('zh-TW', {month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false}).format(date);
}
function setMessage(text, type = '') { message.textContent = text; message.dataset.type = type; }
function updateCounts(tasks) {
  const counts = {all: tasks.length, queued: 0, processing: 0, failed: 0};
  tasks.forEach((task) => { if (task.status in counts) counts[task.status] += 1; });
  Object.entries(counts).forEach(([key, value]) => { const node = document.querySelector(`[data-count="${key}"]`); if (node) node.textContent = value; });
}
function render(tasks) {
  list.replaceChildren();
  const visible = activeFilter ? tasks.filter((task) => task.status === activeFilter) : tasks;
  if (!visible.length) {
    const empty = document.createElement('div'); empty.className = 'queue-empty'; empty.textContent = '目前沒有符合條件的任務。'; list.append(empty); return;
  }
  visible.forEach((task) => {
    const card = template.content.firstElementChild.cloneNode(true);
    card.dataset.status = task.status;
    card.querySelector('.task-name').textContent = taskName(task);
    card.querySelector('.task-kind').textContent = typeLabels[task.task_type] || task.task_type;
    card.querySelector('time').textContent = formatTime(task.created_at);
    card.querySelector('code').textContent = task.task_id.slice(0, 8);
    card.querySelector('.queue-status').textContent = statusLabels[task.status] || task.status;
    const progress = Math.max(0, Math.min(100, Number(task.progress || 0)));
    card.querySelector('.mini-progress i').style.transform = `scaleX(${progress / 100})`;
    card.querySelector('.task-state small').textContent = `${progress}%`;
    const cancel = card.querySelector('.cancel-action');
    const restart = card.querySelector('.restart-action');
    cancel.hidden = task.status !== 'queued';
    restart.hidden = !['failed', 'cancelled'].includes(task.status);
    cancel.addEventListener('click', async () => { if (await window.v2Confirm('確定取消這個等待中的任務？', {confirmLabel: '取消任務'})) updateTask('/api/queue/cancel', task.task_id, cancel); });
    restart.addEventListener('click', () => updateTask('/api/queue/restart', task.task_id, restart));
    card.querySelector('.task-actions').hidden = cancel.hidden && restart.hidden;
    list.append(card);
  });
}
let tasks = [];
async function loadQueue() {
  list.setAttribute('aria-busy', 'true'); refreshButton.disabled = true; setMessage('');
  try {
    const payload = await api.get('/api/queue/list');
    tasks = payload.tasks || [];
    updateCounts(tasks); render(tasks);
  } catch (error) { setMessage(`無法讀取任務：${error.message}`, 'error'); }
  finally { list.setAttribute('aria-busy', 'false'); refreshButton.disabled = false; }
}
async function updateTask(path, taskId, button) {
  button.disabled = true;
  try { const payload = await api.post(path, {task_id: taskId, access_code: ''}); setMessage(payload.message || '任務已更新', 'success'); window.v2Notify(payload.message || '任務已更新'); await loadQueue(); }
  catch (error) { setMessage(error.message, 'error'); button.disabled = false; }
}
document.querySelectorAll('[data-status-filter]').forEach((button) => {
  button.addEventListener('click', () => {
    activeFilter = button.dataset.statusFilter;
    document.querySelectorAll('[data-status-filter]').forEach((item) => { const active = item === button; item.classList.toggle('active', active); item.setAttribute('aria-pressed', String(active)); });
    render(tasks);
  });
});
refreshButton.addEventListener('click', loadQueue);
let refreshTimer = null;
function scheduleRefresh() {
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(loadQueue, 700);
}
['task_log', 'processing_finished', 'server_status_update'].forEach((event) => window.addEventListener(`v2:socket:${event}`, scheduleRefresh));
loadQueue();
