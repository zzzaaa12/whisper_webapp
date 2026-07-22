const raw = document.querySelector('[data-raw-content]');
const markdown = document.querySelector('[data-markdown-content]');
const toggle = document.querySelector('[data-detail-view]');
const bookmark = document.querySelector('[data-detail-bookmark]');
const remove = document.querySelector('[data-detail-delete]');
const message = document.querySelector('[data-detail-message]');
let markdownMode = true;

function setMessage(text, type = '') {
  message.textContent = text;
  message.dataset.type = type;
}

if (window.marked) {
  const safeSource = raw.textContent.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
  markdown.innerHTML = window.marked.parse(safeSource);
} else {
  markdown.textContent = raw.textContent;
  markdown.classList.add('raw-content');
}

toggle.addEventListener('click', () => {
  markdownMode = !markdownMode;
  raw.hidden = markdownMode;
  markdown.hidden = !markdownMode;
  toggle.textContent = markdownMode ? '原始文本' : 'Markdown 顯示';
});

bookmark.addEventListener('click', async () => {
  bookmark.disabled = true;
  setMessage('');
  try {
    const response = await fetch('/api/bookmark', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({filename: bookmark.dataset.filename}),
    });
    const payload = await response.json();
    if (!response.ok || !payload.success) throw new Error(payload.message || '書籤操作失敗');
    const active = bookmark.dataset.bookmarked !== 'true';
    bookmark.dataset.bookmarked = String(active);
    bookmark.textContent = active ? '移除書籤' : '加入書籤';
    setMessage(active ? '已加入書籤。' : '已移除書籤。');
  } catch (error) {
    setMessage(error.message, 'error');
  } finally {
    bookmark.disabled = false;
  }
});

remove.addEventListener('click', async () => {
  if (!(await window.v2Confirm('確定要將這份摘要移到垃圾桶？', {confirmLabel: '移到垃圾桶'}))) return;
  remove.disabled = true;
  setMessage('');
  try {
    const response = await fetch('/api/delete', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({filename: remove.dataset.filename}),
    });
    const payload = await response.json();
    if (!response.ok || !payload.success) throw new Error(payload.message || '刪除失敗');
    location.href = document.querySelector('.detail-back')?.href || '/v2/summaries';
  } catch (error) {
    remove.disabled = false;
    setMessage(error.message, 'error');
  }
});
