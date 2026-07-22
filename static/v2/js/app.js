import {api} from './api-client.js';
import {connectSocket} from './socket-client.js';

const root = document.documentElement;
const sidebar = document.querySelector('#sidebar');
const backdrop = document.querySelector('[data-sidebar-backdrop]');
const menuButton = document.querySelector('[data-sidebar-toggle]');
const connection = document.querySelector('[data-connection-state]');
const confirmDialog = document.querySelector('[data-confirm-dialog]');
const toastRegion = document.querySelector('[data-toast-region]');

window.v2Notify = (text, type = 'success') => {
  const toast = document.createElement('div');
  toast.className = `v2-toast ${type}`; toast.textContent = text;
  toastRegion?.append(toast);
  setTimeout(() => toast.remove(), 3600);
};
window.v2Confirm = (text, {title = '確認操作', confirmLabel = '確認'} = {}) => new Promise((resolve) => {
  if (!confirmDialog?.showModal) { resolve(window.confirm(text)); return; }
  confirmDialog.querySelector('[data-confirm-title]').textContent = title;
  confirmDialog.querySelector('[data-confirm-message]').textContent = text;
  confirmDialog.querySelector('[data-confirm-submit]').textContent = confirmLabel;
  const close = () => { confirmDialog.removeEventListener('close', close); resolve(confirmDialog.returnValue === 'confirm'); };
  confirmDialog.addEventListener('close', close); confirmDialog.showModal();
});

function setSidebar(open) {
  sidebar?.classList.toggle('open', open);
  backdrop?.classList.toggle('visible', open);
  menuButton?.setAttribute('aria-expanded', String(open));
}

menuButton?.addEventListener('click', () => setSidebar(!sidebar?.classList.contains('open')));
backdrop?.addEventListener('click', () => setSidebar(false));

const savedTheme = localStorage.getItem('v2-theme');
if (savedTheme) root.dataset.theme = savedTheme;
document.querySelector('[data-theme-toggle]')?.addEventListener('click', () => {
  root.dataset.theme = root.dataset.theme === 'light' ? 'dark' : 'light';
  localStorage.setItem('v2-theme', root.dataset.theme);
});

const socketEvents = ['update_log', 'task_log', 'server_status_update', 'gpu_status_update', 'processing_finished', 'access_code_error'];
const socketHandlers = Object.fromEntries(socketEvents.map((event) => [event, (payload) => {
  window.dispatchEvent(new CustomEvent(`v2:socket:${event}`, {detail: payload}));
}]));
socketHandlers.connect = () => {
  connection?.classList.add('online');
  const label = connection?.querySelector('span');
  if (label) label.textContent = '即時連線正常';
};
socketHandlers.disconnect = () => {
  connection?.classList.remove('online');
  const label = connection?.querySelector('span');
  if (label) label.textContent = '即時連線中斷';
};
window.v2Socket = connectSocket(socketHandlers);

async function loadSystemSnapshot() {
  const hasMetrics = document.querySelector('[data-completed-count], [data-queued-count], [data-processing-count], [data-failed-count]');
  if (!hasMetrics) return;
  try {
    await api.health();
  } catch (error) {
    if (document.querySelector('[data-dashboard-tasks]')) window.v2Notify(`API 無法連線：${error.message}`, 'error');
  }

  try {
    const payload = await api.queueStatus();
    const status = payload.status || {};
    const queued = status.queued_count ?? status.queued ?? 0;
    const processing = status.processing_count ?? status.processing ?? 0;
    const queuedNode = document.querySelector('[data-queued-count]');
    const processingNode = document.querySelector('[data-processing-count]');
    const completedNode = document.querySelector('[data-completed-count]');
    const failedNode = document.querySelector('[data-failed-count]');
    if (queuedNode) queuedNode.textContent = String(queued);
    if (processingNode) processingNode.textContent = String(processing);
    if (completedNode) completedNode.textContent = String(status.completed ?? 0);
    if (failedNode) failedNode.textContent = String(status.failed ?? 0);
  } catch (_) {
    const queuedNode = document.querySelector('[data-queued-count]');
    const processingNode = document.querySelector('[data-processing-count]');
    const completedNode = document.querySelector('[data-completed-count]');
    const failedNode = document.querySelector('[data-failed-count]');
    if (queuedNode) queuedNode.textContent = '—';
    if (processingNode) processingNode.textContent = '—';
    if (completedNode) completedNode.textContent = '—';
    if (failedNode) failedNode.textContent = '—';
  }
}

function dashboardTaskName(task) { return task.result?.video_title || task.data?.title || task.data?.display_name || task.data?.original_filename || '處理任務'; }
async function loadDashboardLists() {
  const taskRoot = document.querySelector('[data-dashboard-tasks]');
  const summaryRoot = document.querySelector('[data-dashboard-summaries]');
  if (!taskRoot || !summaryRoot) return;
  try {
    const payload = await api.get('/api/queue/list?limit=20');
    const order = {processing: 0, queued: 1, failed: 2};
    const active = (payload.tasks || []).filter((task) => ['queued', 'processing', 'failed'].includes(task.status)).sort((left, right) => order[left.status] - order[right.status]).slice(0, 5);
    taskRoot.replaceChildren(...active.map((task) => {
      const link = document.createElement('a'); link.href = '/v2/queue'; link.className = 'dashboard-row';
      const name = document.createElement('strong'); name.textContent = dashboardTaskName(task);
      const status = document.createElement('span'); status.textContent = ({queued: '等待中', processing: '處理中', failed: '失敗'})[task.status];
      link.append(name, status); return link;
    }));
    if (!active.length) taskRoot.innerHTML = '<p class="dashboard-empty">目前沒有待處理或失敗任務。</p>';
  } catch (error) { taskRoot.innerHTML = '<p class="dashboard-empty">任務讀取失敗。</p>'; }
  try {
    const payload = await api.post('/api/summaries/list', {page: 1, per_page: 5});
    const items = payload.summaries || [];
    summaryRoot.replaceChildren(...items.map((item) => {
      const link = document.createElement('a'); link.href = `/v2/summaries/${encodeURIComponent(item.filename)}?return=${encodeURIComponent('/v2/')}`; link.className = 'dashboard-row';
      const title = document.createElement('strong'); title.textContent = item.title;
      const channel = document.createElement('span'); channel.textContent = item.channel_display || item.channel || '未知頻道';
      link.append(title, channel); return link;
    }));
    if (!items.length) summaryRoot.innerHTML = '<p class="dashboard-empty">目前沒有摘要。</p>';
  } catch (error) { summaryRoot.innerHTML = '<p class="dashboard-empty">摘要讀取失敗。</p>'; }
}

loadSystemSnapshot();
loadDashboardLists();
