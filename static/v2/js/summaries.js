import {api} from './api-client.js';

const list = document.querySelector('[data-summary-list]');
const message = document.querySelector('[data-summary-message]');
const count = document.querySelector('[data-summary-count]');
const pageStatus = document.querySelector('[data-page-status]');
const previous = document.querySelector('[data-previous-page]');
const next = document.querySelector('[data-next-page]');
const search = document.querySelector('#summary-search');
const channel = document.querySelector('#channel-filter');
const type = document.querySelector('#summary-type');
const bookmarkedOnly = document.querySelector('[data-bookmarked-only]');
const template = document.querySelector('#summary-row-template');
const state = {page: 1, channel: '', pagination: {}, request: null};

function setMessage(text, kind = '') { message.textContent = text; message.dataset.type = kind; }
function formatTime(value) { return String(value || '').slice(0, 16); }
function readUrl() {
  const params = new URLSearchParams(location.search);
  state.page = Math.max(1, Number(params.get('page')) || 1);
  state.channel = params.get('channel') || '';
  search.value = params.get('search') || '';
  type.value = ['all', 'auto', 'manual'].includes(params.get('type')) ? params.get('type') : 'all';
  bookmarkedOnly.checked = params.get('bookmarked') === '1';
}
function writeUrl() {
  const params = new URLSearchParams();
  if (state.page > 1) params.set('page', state.page);
  if (state.channel) params.set('channel', state.channel);
  if (search.value.trim()) params.set('search', search.value.trim());
  if (type.value !== 'all') params.set('type', type.value);
  if (bookmarkedOnly.checked) params.set('bookmarked', '1');
  history.replaceState(null, '', `${location.pathname}${params.size ? `?${params}` : ''}`);
}
function renderChannels(channels) {
  const selected = state.channel;
  channel.replaceChildren(new Option('全部頻道', ''));
  channels.forEach((item) => channel.add(new Option(`${item.display_name} (${item.count})`, item.name)));
  channel.value = selected;
}
function selectedFilenames() { return [...document.querySelectorAll('.summary-checkbox:checked')].map((node) => node.dataset.filename); }
function updateSelection() {
  const selected = selectedFilenames();
  document.querySelector('[data-batch-toolbar]').hidden = selected.length === 0;
  document.querySelector('[data-selected-count]').textContent = `已選擇 ${selected.length} 個項目`;
}
function render(items) {
  list.replaceChildren();
  if (!items.length) { const empty = document.createElement('div'); empty.className = 'summary-empty'; empty.textContent = '目前沒有符合條件的摘要。'; list.append(empty); return; }
  items.forEach((item) => {
    const row = template.content.firstElementChild.cloneNode(true);
    const encoded = encodeURIComponent(item.filename);
    const main = row.querySelector('.summary-title-link');
    main.href = `/v2/summaries/${encoded}?return=${encodeURIComponent(location.pathname + location.search)}`;
    row.querySelector('.summary-title').textContent = item.title;
    const checkbox = row.querySelector('.summary-checkbox');
    checkbox.dataset.filename = item.filename;
    checkbox.setAttribute('aria-label', `選取 ${item.title}`);
    checkbox.addEventListener('change', updateSelection);
    const channelButton = row.querySelector('.summary-channel');
    channelButton.textContent = item.channel_display || item.channel || '未知頻道';
    channelButton.addEventListener('click', (event) => { event.preventDefault(); state.channel = item.channel || ''; channel.value = state.channel; state.page = 1; load(); });
    row.querySelector('time').textContent = formatTime(item.created_at);
    row.querySelector('.auto-label').hidden = !item.is_auto;
    const preview = row.querySelector('.summary-preview');
    preview.textContent = item.preview || '';
    preview.hidden = !item.preview;
    const bookmark = row.querySelector('.bookmark-action');
    bookmark.textContent = item.is_bookmarked ? '移除書籤' : '加入書籤';
    bookmark.addEventListener('click', () => update('/api/bookmark', {filename: item.filename}, bookmark));
    const download = row.querySelector('.download-action');
    download.href = `/download/summary/${encoded}`; download.download = '';
    const subtitle = row.querySelector('.subtitle-action');
    if (item.has_subtitle && item.subtitle_filename) {
      subtitle.hidden = false;
      subtitle.href = `/download/subtitle/${encodeURIComponent(item.subtitle_filename)}`;
      subtitle.download = '';
    }
    const remove = row.querySelector('.delete-action');
    remove.addEventListener('click', async () => {
      if (!(await window.v2Confirm(`確定將「${item.title}」移到垃圾桶？`, {confirmLabel: '移到垃圾桶'}))) return;
      await update('/api/delete', {filename: item.filename}, remove);
    });
    list.append(row);
  });
  updateSelection();
}
function renderPagination() {
  const p = state.pagination;
  previous.disabled = !p.has_prev; next.disabled = !p.has_next;
  pageStatus.textContent = p.total_pages ? `第 ${p.page} / ${p.total_pages} 頁` : '第 0 頁';
  count.textContent = `共 ${p.total_count || 0} 份摘要`;
}
async function load() {
  state.request?.abort();
  state.request = new AbortController();
  list.setAttribute('aria-busy', 'true'); setMessage('');
  try {
    const payload = await fetch('/api/summaries/list', {method: 'POST', headers: {'Content-Type': 'application/json'}, signal: state.request.signal, body: JSON.stringify({page: state.page, per_page: 30, channel: state.channel, search: search.value.trim(), bookmarked_only: bookmarkedOnly.checked, summary_type: type.value})});
    const data = await payload.json();
    if (!payload.ok || !data.success) throw new Error(data.message || '摘要載入失敗');
    state.pagination = data.pagination || {}; state.page = state.pagination.page || 1;
    renderChannels(data.channels || []); render(data.summaries || []); renderPagination(); writeUrl();
  } catch (error) { if (error.name !== 'AbortError') setMessage(error.message, 'error'); }
  finally { list.setAttribute('aria-busy', 'false'); state.request = null; }
}
async function update(path, body, button) {
  button.disabled = true;
  try { const payload = await api.post(path, body); setMessage(payload.message || '操作完成', 'success'); await load(); }
  catch (error) { setMessage(error.message, 'error'); button.disabled = false; }
}
let searchTimer;
search.addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => { state.page = 1; load(); }, 300); });
type.addEventListener('change', () => { state.page = 1; load(); });
channel.addEventListener('change', () => { state.channel = channel.value; state.page = 1; load(); });
bookmarkedOnly.addEventListener('change', () => { state.page = 1; load(); });
document.querySelector('[data-refresh-summaries]').addEventListener('click', load);
document.querySelector('[data-clear-filters]').addEventListener('click', () => { state.page = 1; state.channel = ''; search.value = ''; channel.value = ''; type.value = 'all'; bookmarkedOnly.checked = false; load(); });
previous.addEventListener('click', () => { if (state.pagination.has_prev) { state.page -= 1; load(); } });
next.addEventListener('click', () => { if (state.pagination.has_next) { state.page += 1; load(); } });
document.querySelector('[data-cancel-selection]').addEventListener('click', () => { document.querySelectorAll('.summary-checkbox').forEach((node) => { node.checked = false; }); updateSelection(); });
document.querySelector('[data-batch-bookmark]').addEventListener('click', async (event) => { const filenames = selectedFilenames(); if (filenames.length) await update('/api/batch-bookmark', {filenames}, event.currentTarget); });
document.querySelector('[data-batch-delete]').addEventListener('click', async (event) => { const filenames = selectedFilenames(); if (filenames.length && await window.v2Confirm(`確定將 ${filenames.length} 份摘要移到垃圾桶？`, {confirmLabel: '移到垃圾桶'})) await update('/api/batch-delete', {filenames}, event.currentTarget); });
function setView(view) {
  const card = view === 'card'; list.classList.toggle('card-view', card); localStorage.setItem('v2-summary-view', card ? 'card' : 'list');
  document.querySelectorAll('[data-view]').forEach((button) => { const active = button.dataset.view === (card ? 'card' : 'list'); button.classList.toggle('active', active); button.setAttribute('aria-pressed', String(active)); });
}
document.querySelectorAll('[data-view]').forEach((button) => button.addEventListener('click', () => setView(button.dataset.view)));
readUrl(); setView(localStorage.getItem('v2-summary-view') === 'list' ? 'list' : 'card'); load();
