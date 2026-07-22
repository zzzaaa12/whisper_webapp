export class ApiError extends Error {
  constructor(message, {status = 0, payload = null} = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.payload = payload;
  }
}

async function request(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  const response = await fetch(path, {...options, headers});
  const payload = await response.json().catch(() => null);
  if (!response.ok || payload?.success === false || payload?.status === 'error') {
    throw new ApiError(payload?.message || `Request failed (${response.status})`, {status: response.status, payload});
  }
  return payload;
}

export const api = Object.freeze({
  health: () => request('/api/health'),
  queueStatus: () => request('/api/queue/status'),
  get: (path) => request(path),
  post: (path, body) => request(path, {method: 'POST', body: JSON.stringify(body)}),
  upload: (path, formData) => request(path, {method: 'POST', body: formData}),
});

