const list = document.querySelector('[data-bookmark-list]');
const search = document.querySelector('#bookmark-search');
const count = document.querySelector('[data-bookmark-count]');
const message = document.querySelector('[data-bookmark-message]');
const previous = document.querySelector('[data-bookmark-previous]');
const next = document.querySelector('[data-bookmark-next]');
const pageLabel = document.querySelector('[data-bookmark-page]');
const template = document.querySelector('#bookmark-card-template');
const state = {page: 1, pagination: {}};

function formatTime(value) { return String(value || '').slice(0, 16); }
function setMessage(text, type = '') { message.textContent = text; message.dataset.type = type; }
function detailUrl(filename) {
  const back = `${location.pathname}${location.search}`;
  return `/v2/summaries/${encodeURIComponent(filename)}?return=${encodeURIComponent(back)}`;
}
function render(items) {
  list.replaceChildren();
  if (!items.length) { const empty = document.createElement('div'); empty.className = 'summary-empty'; empty.textContent = '目前沒有符合條件的書籤。'; list.append(empty); return; }
  items.forEach((item) => {
    const card = template.content.firstElementChild.cloneNode(true);
    card.querySelector('.summary-title-link').href = detailUrl(item.filename);
    card.querySelector('.summary-title').textContent = item.title;
    card.querySelector('.summary-channel-label').textContent = item.channel_display || item.channel || '未知頻道';
    card.querySelector('time').textContent = formatTime(item.created_at);
    const preview = card.querySelector('.summary-preview'); preview.textContent = item.preview || ''; preview.hidden = !item.preview;
    card.querySelector('.download-action').href = `/download/summary/${encodeURIComponent(item.filename)}`;
    card.querySelector('.bookmark-action').addEventListener('click', async (event) => {
      if (!(await window.v2Confirm('確定要移除這個書籤？', {confirmLabel: '移除'}))) return;
      event.currentTarget.disabled = true;
      try {
        const response = await fetch('/api/bookmark', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({filename: item.filename})});
        const payload = await response.json();
        if (!response.ok || !payload.success) throw new Error(payload.message || '移除書籤失敗');
        window.v2Notify('已移除書籤。'); await load();
      } catch (error) { setMessage(error.message, 'error'); event.currentTarget.disabled = false; }
    });
    list.append(card);
  });
}
async function load() {
  list.setAttribute('aria-busy', 'true'); setMessage('');
  try {
    const response = await fetch('/api/summaries/list', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({page: state.page, per_page: 30, search: search.value.trim(), bookmarked_only: true})});
    const payload = await response.json();
    if (!response.ok || !payload.success) throw new Error(payload.message || '書籤載入失敗');
    state.pagination = payload.pagination || {}; state.page = state.pagination.page || 1;
    count.textContent = `共 ${state.pagination.total_count || 0} 個書籤`;
    pageLabel.textContent = `第 ${state.page} / ${state.pagination.total_pages || 1} 頁`;
    previous.disabled = !state.pagination.has_prev; next.disabled = !state.pagination.has_next;
    render(payload.summaries || []);
  } catch (error) { setMessage(error.message, 'error'); }
  finally { list.setAttribute('aria-busy', 'false'); }
}
let timer;
search.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(() => { state.page = 1; load(); }, 300); });
previous.addEventListener('click', () => { if (state.pagination.has_prev) { state.page -= 1; load(); } });
next.addEventListener('click', () => { if (state.pagination.has_next) { state.page += 1; load(); } });
document.querySelector('[data-refresh-bookmarks]').addEventListener('click', load);
load();
