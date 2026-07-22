import {api} from './api-client.js';

const form = document.querySelector('[data-task-form]');
const uploadForm = document.querySelector('[data-upload-form]');
const urlInput = document.querySelector('#task-url');
const fileInput = document.querySelector('#media-file');
const fileNameNode = document.querySelector('[data-file-name]');
const message = document.querySelector('[data-form-message]');
const uploadMessage = document.querySelector('[data-upload-message]');
const uploadProgress = document.querySelector('[data-upload-progress]');
const uploadStatus = document.querySelector('[data-upload-status]');
const uploadPercent = document.querySelector('[data-upload-percent]');
const uploadBar = uploadProgress?.querySelector('progress');
const cancelUploadButton = document.querySelector('[data-cancel-upload]');
const stageList = document.querySelector('[data-stage-list]');
const progressCard = document.querySelector('[data-progress-card]');
const taskIdNode = document.querySelector('[data-task-id]');
const taskTitleNode = document.querySelector('[data-task-title]');
const taskStatusNode = document.querySelector('[data-task-status] span');
const logNode = document.querySelector('[data-task-log]');
const submitButton = form?.querySelector('button[type="submit"]');
const uploadButton = uploadForm?.querySelector('button[type="submit"]');
let activeTaskId = sessionStorage.getItem('v2-active-task-id');
let activeTaskType = sessionStorage.getItem('v2-active-task-type') || 'url';
let pollTimer = null;
let uploadRequest = null;
const stages = ['queued', 'metadata', 'subtitle', 'download', 'transcription', 'summary'];

function setMessage(node, text, type = '') { node.textContent = text; node.dataset.type = type; }
function setTaskType(type) {
  activeTaskType = type === 'upload_media' ? 'upload_media' : 'url';
  stageList.classList.toggle('upload-task', activeTaskType === 'upload_media');
}
function appendLog(text, type = 'info') {
  if (!text) return;
  if (logNode.querySelector('p')) logNode.replaceChildren();
  const item = document.createElement('div');
  item.className = `log-line ${type}`;
  item.textContent = text;
  logNode.append(item);
  logNode.scrollTop = logNode.scrollHeight;
}
function activateStage(current, completed = false) {
  const index = stages.indexOf(current);
  document.querySelectorAll('[data-stage]').forEach((node) => {
    const nodeIndex = stages.indexOf(node.dataset.stage);
    node.classList.toggle('done', completed || nodeIndex < index);
    node.classList.toggle('current', !completed && nodeIndex === index);
  });
}
function stageFromTask(task) {
  if (task.status === 'queued') return 'queued';
  if (task.status === 'completed') return 'summary';
  const progress = Number(task.progress || 0);
  if (activeTaskType === 'upload_media' || task.task_type === 'upload_media') {
    return progress >= 80 ? 'summary' : 'transcription';
  }
  if (progress >= 80) return 'summary';
  if (progress >= 60) return 'transcription';
  if (progress >= 50) return 'download';
  if (progress >= 20) return 'subtitle';
  return 'metadata';
}
function beginTask(payload, type = 'url') {
  activeTaskId = payload.task_id;
  setTaskType(type);
  sessionStorage.setItem('v2-active-task-id', activeTaskId);
  sessionStorage.setItem('v2-active-task-type', activeTaskType);
  progressCard.hidden = false;
  taskIdNode.textContent = activeTaskId;
  taskTitleNode.textContent = payload.title || payload.display_name || '處理任務';
  taskStatusNode.textContent = payload.queue_position > 1 ? `排隊第 ${payload.queue_position} 位` : '已加入佇列';
  activateStage('queued');
  appendLog(payload.message || '任務已加入佇列', 'success');
  startPolling();
}
function renderTask(task) {
  progressCard.hidden = false;
  if (task.task_type) setTaskType(task.task_type);
  taskIdNode.textContent = task.task_id || activeTaskId;
  taskTitleNode.textContent = task.data?.title || task.data?.display_name || '處理任務';
  taskStatusNode.textContent = ({queued: '等待中', processing: '處理中', completed: '已完成', failed: '失敗', cancelled: '已取消'})[task.status] || task.status;
  const terminal = ['completed', 'failed', 'cancelled'].includes(task.status);
  activateStage(stageFromTask(task), task.status === 'completed');
  if (terminal) {
    clearInterval(pollTimer); pollTimer = null;
    activeTaskId = null;
    sessionStorage.removeItem('v2-active-task-id');
    sessionStorage.removeItem('v2-active-task-type');
    if (task.error_message) appendLog(task.error_message, 'error');
  }
}
async function pollTask() {
  if (!activeTaskId) return;
  try { const payload = await api.get(`/api/queue/task/${encodeURIComponent(activeTaskId)}`); renderTask(payload.task); }
  catch (error) { appendLog(`無法更新任務狀態：${error.message}`, 'error'); }
}
function startPolling() { clearInterval(pollTimer); pollTask(); pollTimer = setInterval(pollTask, 2000); }

window.addEventListener('v2:socket:task_log', ({detail: payload}) => {
  if (!activeTaskId || payload?.task_id === activeTaskId) appendLog(payload?.log, payload?.type);
});
window.addEventListener('v2:socket:update_log', ({detail: payload}) => {
  if (activeTaskId) appendLog(payload?.log, payload?.type);
});

form?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const url = urlInput.value.trim();
  if (!/^https?:\/\//i.test(url)) { setMessage(message, '請輸入包含 http:// 或 https:// 的完整網址。', 'error'); urlInput.focus(); return; }
  submitButton.disabled = true; setMessage(message, '正在加入佇列…');
  try {
    const payload = await api.post('/api/process', {youtube_url: url, access_code: ''});
    if (payload.status === 'completed') { setMessage(message, '已找到現有摘要，不需要重複處理。', 'success'); return; }
    beginTask(payload, 'url');
    setMessage(message, '任務已成功加入佇列。', 'success'); urlInput.value = '';
  } catch (error) { setMessage(message, error.message, 'error'); }
  finally { submitButton.disabled = false; }
});

fileInput?.addEventListener('change', () => { fileNameNode.textContent = fileInput.files?.[0]?.name || '選擇音訊或影片'; });
uploadForm?.addEventListener('submit', (event) => {
  event.preventDefault();
  const file = fileInput.files?.[0];
  if (!file) { setMessage(uploadMessage, '請先選擇要上傳的檔案。', 'error'); fileInput.focus(); return; }
  if (file.size > 2 * 1024 * 1024 * 1024) { setMessage(uploadMessage, '檔案不可超過 2 GB。', 'error'); return; }
  const body = new FormData();
  body.append('media_file', file);
  body.append('access_code', '');
  const xhr = new XMLHttpRequest();
  uploadRequest = xhr;
  xhr.open('POST', '/api/upload_media');
  uploadButton.disabled = true;
  cancelUploadButton.hidden = false;
  uploadProgress.hidden = false;
  uploadBar.value = 0;
  uploadPercent.textContent = '0%';
  uploadStatus.textContent = '正在上傳';
  setMessage(uploadMessage, '');
  xhr.upload.addEventListener('progress', ({lengthComputable, loaded, total}) => {
    if (!lengthComputable) return;
    const percent = Math.round((loaded / total) * 100);
    uploadBar.value = percent;
    uploadBar.textContent = `${percent}%`;
    uploadPercent.textContent = `${percent}%`;
  });
  xhr.addEventListener('load', () => {
    let payload = {};
    try { payload = JSON.parse(xhr.responseText); } catch (_) { payload = {}; }
    if (xhr.status >= 200 && xhr.status < 300 && payload.task_id) {
      uploadBar.value = 100;
      uploadPercent.textContent = '100%';
      uploadStatus.textContent = '上傳完成';
      setMessage(uploadMessage, '檔案已上傳並加入佇列。', 'success');
      beginTask(payload, 'upload_media');
      uploadForm.reset();
      fileNameNode.textContent = '選擇音訊或影片';
    } else setMessage(uploadMessage, payload.error || payload.message || '檔案上傳失敗。', 'error');
  });
  xhr.addEventListener('error', () => setMessage(uploadMessage, '網路中斷，檔案上傳失敗。', 'error'));
  xhr.addEventListener('abort', () => { uploadStatus.textContent = '已取消'; setMessage(uploadMessage, '已取消上傳。'); });
  xhr.addEventListener('loadend', () => { uploadRequest = null; uploadButton.disabled = false; cancelUploadButton.hidden = true; });
  xhr.send(body);
});
cancelUploadButton?.addEventListener('click', () => uploadRequest?.abort());

document.querySelector('[data-clear-task]')?.addEventListener('click', () => {
  sessionStorage.removeItem('v2-active-task-id'); activeTaskId = null;
  sessionStorage.removeItem('v2-active-task-type');
  clearInterval(pollTimer); progressCard.hidden = true;
});
if (activeTaskId) {
  setTaskType(activeTaskType);
  progressCard.hidden = false; taskIdNode.textContent = activeTaskId; startPolling();
}
