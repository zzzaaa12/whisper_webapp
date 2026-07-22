export function connectSocket(handlers = {}) {
  if (typeof window.io !== 'function') return null;
  const socket = window.io();
  const knownEvents = [
    'update_log', 'task_log', 'server_status_update', 'gpu_status_update',
    'processing_finished', 'access_code_error',
  ];
  knownEvents.forEach((event) => socket.on(event, (payload) => handlers[event]?.(payload)));
  socket.on('connect', () => handlers.connect?.());
  socket.on('disconnect', () => handlers.disconnect?.());
  return Object.freeze({
    startProcessing: (payload) => socket.emit('start_processing', payload),
    cancelProcessing: () => socket.emit('cancel_processing'),
    clearLogs: () => socket.emit('clear_logs'),
    requestGpuStatus: () => socket.emit('request_gpu_status'),
    raw: socket,
  });
}
