document.addEventListener('DOMContentLoaded', () => {

    // Theme toggle is handled by theme-toggle.js

    // ==================== Socket.IO and Main Functionality ====================
    const socket = io();

    const form = document.getElementById('process-form');
    const urlInput = document.getElementById('audio_url');
    const urlInputMobile = document.getElementById('audio_url_mobile');
    const accessCodeInput = document.getElementById('access_code');
    const accessCodeInputMobile = document.getElementById('access_code_mobile');
    const submitBtn = document.getElementById('submit-btn');
    const submitBtnMobile = document.getElementById('submit-btn-mobile');
    const cancelBtn = document.getElementById('cancel-btn');
    const cancelBtnMobile = document.getElementById('cancel-btn-mobile');
    const logContainer = document.getElementById('log-container');
    const statusBar = document.getElementById('status-footer');
    const videoInfoCard = document.getElementById('video-info-card');
    const videoThumbnail = document.getElementById('video-thumbnail');
    const videoTitle = document.getElementById('video-title');
    const videoUploader = document.getElementById('video-uploader');
    const videoDetails = document.getElementById('video-details');
    const scheduleGrid = document.getElementById('schedule-grid');
    const scheduleEnabledInput = document.getElementById('schedule-enabled');
    const scheduleStatusBadge = document.getElementById('schedule-status-badge');
    const scheduleNextAllowed = document.getElementById('schedule-next-allowed');
    const scheduleTimezone = document.getElementById('schedule-timezone');
    const scheduleSaveBtn = document.getElementById('schedule-save-btn');
    const scheduleDefaultBtn = document.getElementById('schedule-default-btn');
    const scheduleSelectAllBtn = document.getElementById('schedule-select-all-btn');
    const scheduleClearAllBtn = document.getElementById('schedule-clear-all-btn');
    const weekdayLabels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    const highlightedHours = new Set([0, 6, 12, 18]);
    let transcriptionSchedule = null;

    function createEmptyScheduleGrid() {
        const grid = {};
        for (let day = 0; day < 7; day += 1) {
            grid[String(day)] = Array(48).fill(false);
        }
        return grid;
    }

    function buildDefaultScheduleState() {
        const grid = createEmptyScheduleGrid();
        const defaultSlots = [[0, 15], [25, 26], [37, 39]];
        Object.keys(grid).forEach((day) => {
            defaultSlots.forEach(([start, end]) => {
                for (let slot = start; slot <= end; slot += 1) {
                    grid[day][slot] = true;
                }
            });
        });

        return {
            enabled: true,
            timezone: 'Asia/Taipei',
            apply_to_task_types: ['youtube', 'upload_media'],
            grid,
            is_allowed_now: false,
            next_allowed_at: null
        };
    }

    function getScheduleAccessCode() {
        return (accessCodeInput ? accessCodeInput.value.trim() : '') ||
            (accessCodeInputMobile ? accessCodeInputMobile.value.trim() : '');
    }

    function injectScheduleLinks() {
        const mobileQueueLink = document.querySelector('.d-md-none a[href="/queue"]');
        if (mobileQueueLink && !document.querySelector('.d-md-none a[href="/transcription-schedule"]')) {
            const scheduleLink = document.createElement('a');
            scheduleLink.href = '/transcription-schedule';
            scheduleLink.className = 'btn btn-outline-dark btn-sm';
            scheduleLink.textContent = 'Schedule';
            mobileQueueLink.insertAdjacentElement('afterend', scheduleLink);
        }

        const desktopQueueLink = document.querySelector('.d-none.d-md-block a[href="/queue"]');
        if (desktopQueueLink && !document.querySelector('.d-none.d-md-block a[href="/transcription-schedule"]')) {
            const scheduleLink = document.createElement('a');
            scheduleLink.href = '/transcription-schedule';
            scheduleLink.className = 'btn btn-outline-dark btn-sm ms-2';
            scheduleLink.textContent = 'Schedule';
            desktopQueueLink.insertAdjacentElement('afterend', scheduleLink);
        }
    }

    function formatScheduleDate(value) {
        if (!value) {
            return '-';
        }

        const parsed = new Date(value);
        if (Number.isNaN(parsed.getTime())) {
            return value;
        }

        return parsed.toLocaleString();
    }

    function updateScheduleStatusUI() {
        if (!transcriptionSchedule || !scheduleEnabledInput || !scheduleStatusBadge || !scheduleNextAllowed || !scheduleTimezone) {
            return;
        }

        const enabled = Boolean(transcriptionSchedule.enabled);
        const isAllowedNow = Boolean(transcriptionSchedule.is_allowed_now);
        scheduleEnabledInput.checked = enabled;
        scheduleTimezone.textContent = `Timezone: ${transcriptionSchedule.timezone || 'Asia/Taipei'}`;

        if (!enabled) {
            scheduleStatusBadge.className = 'badge text-bg-secondary';
            scheduleStatusBadge.textContent = 'Schedule disabled';
        } else if (isAllowedNow) {
            scheduleStatusBadge.className = 'badge text-bg-success';
            scheduleStatusBadge.textContent = 'Allowed now';
        } else {
            scheduleStatusBadge.className = 'badge text-bg-warning';
            scheduleStatusBadge.textContent = 'Blocked now';
        }

        scheduleNextAllowed.textContent = `Next allowed: ${formatScheduleDate(transcriptionSchedule.next_allowed_at)}`;
    }

    function renderScheduleGrid() {
        if (!scheduleGrid || !transcriptionSchedule || !transcriptionSchedule.grid) {
            return;
        }

        const table = document.createElement('table');
        table.className = 'table table-sm schedule-table align-middle';

        const thead = document.createElement('thead');
        const headRow = document.createElement('tr');
        const cornerCell = document.createElement('th');
        cornerCell.className = 'schedule-day-label';
        cornerCell.textContent = 'Day / Time';
        headRow.appendChild(cornerCell);

        for (let slot = 0; slot < 48; slot += 1) {
            const th = document.createElement('th');
            th.className = 'schedule-slot-label';
            if (slot % 2 === 0 && highlightedHours.has(slot / 2)) {
                th.textContent = `${String(slot / 2).padStart(2, '0')}:00`;
            } else {
                th.textContent = '';
            }
            headRow.appendChild(th);
        }

        thead.appendChild(headRow);
        table.appendChild(thead);

        const tbody = document.createElement('tbody');
        weekdayLabels.forEach((label, dayIndex) => {
            const row = document.createElement('tr');
            const dayCell = document.createElement('th');
            dayCell.className = 'schedule-day-label';
            dayCell.textContent = label;
            row.appendChild(dayCell);

            transcriptionSchedule.grid[String(dayIndex)].forEach((enabled, slotIndex) => {
                const cell = document.createElement('td');
                const button = document.createElement('button');
                button.type = 'button';
                button.className = `schedule-slot${enabled ? ' active' : ''}`;
                button.dataset.day = String(dayIndex);
                button.dataset.slot = String(slotIndex);
                button.title = `${label} ${String(Math.floor(slotIndex / 2)).padStart(2, '0')}:${slotIndex % 2 === 0 ? '00' : '30'}`;
                cell.appendChild(button);
                row.appendChild(cell);
            });

            tbody.appendChild(row);
        });

        table.appendChild(tbody);
        scheduleGrid.innerHTML = '';
        scheduleGrid.appendChild(table);
        updateScheduleStatusUI();
    }

    async function loadTranscriptionSchedule() {
        if (!scheduleGrid) {
            return;
        }

        try {
            const response = await fetch('/api/system/transcription-schedule');
            const result = await response.json();
            if (!result.success) {
                throw new Error(result.message || 'Unable to load transcription schedule.');
            }

            transcriptionSchedule = result.schedule;
            renderScheduleGrid();
        } catch (error) {
            transcriptionSchedule = buildDefaultScheduleState();
            renderScheduleGrid();
            appendLog(`Failed to load transcription schedule: ${error.message}`, 'error');
        }
    }

    function setAllScheduleSlots(value) {
        if (!transcriptionSchedule || !transcriptionSchedule.grid) {
            return;
        }

        Object.keys(transcriptionSchedule.grid).forEach((day) => {
            transcriptionSchedule.grid[day] = transcriptionSchedule.grid[day].map(() => value);
        });
        renderScheduleGrid();
    }

    function applyDefaultSchedule() {
        transcriptionSchedule = buildDefaultScheduleState();
        renderScheduleGrid();
    }

    async function saveTranscriptionSchedule() {
        if (!transcriptionSchedule) {
            return;
        }

        const payload = {
            access_code: getScheduleAccessCode(),
            schedule: {
                enabled: scheduleEnabledInput.checked,
                timezone: transcriptionSchedule.timezone || 'Asia/Taipei',
                apply_to_task_types: transcriptionSchedule.apply_to_task_types || ['youtube', 'upload_media'],
                weekdays: transcriptionSchedule.grid
            }
        };

        scheduleSaveBtn.disabled = true;

        try {
            const response = await fetch('/api/system/transcription-schedule', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(payload)
            });

            const result = await response.json();
            if (!response.ok || !result.success) {
                throw new Error(result.message || 'Unable to save transcription schedule.');
            }

            transcriptionSchedule = result.schedule;
            renderScheduleGrid();
            appendLog('Transcription schedule saved.', 'success');
        } catch (error) {
            appendLog(`Failed to save transcription schedule: ${error.message}`, 'error');
        } finally {
            scheduleSaveBtn.disabled = false;
        }
    }

    const appendLog = (message, type = 'info') => {
        const now = new Date();
        const month = String(now.getMonth() + 1).padStart(2, '0');
        const day = String(now.getDate()).padStart(2, '0');
        const hours = String(now.getHours()).padStart(2, '0');
        const minutes = String(now.getMinutes()).padStart(2, '0');
        const seconds = String(now.getSeconds()).padStart(2, '0');
        const timestamp = `${month}/${day} ${hours}:${minutes}:${seconds}`;

        const logEntry = document.createElement('div');

        let colorClass = '';
        if (type === 'error') {
            colorClass = 'text-danger';
        } else if (type === 'success') {
            colorClass = 'text-success';
        }

        logEntry.textContent = `[${timestamp}] ${message}`;
        if(colorClass) {
            logEntry.classList.add(colorClass);
        }

        logContainer.appendChild(logEntry);

        // 智能滾動: 如果使用者沒有手動滾動，則自動滾動到底部
        const isAtBottom = logContainer.scrollTop + logContainer.clientHeight >= logContainer.scrollHeight - 10;
        if (isAtBottom) {
            logContainer.scrollTop = logContainer.scrollHeight;
        }
    };

    // 監聽滾動事件，用於智能滾動判斷
    let userScrolled = false;
    logContainer.addEventListener('scroll', () => {
        const isAtBottom = logContainer.scrollTop + logContainer.clientHeight >= logContainer.scrollHeight - 10;
        userScrolled = !isAtBottom;
    });

    // 滾動到底部按鈕功能
    window.scrollToBottom = function() {
        logContainer.scrollTop = logContainer.scrollHeight;
        userScrolled = false;
    };

    // 清除日誌功能
    window.clearLog = function() {
        if (confirm('確定要清除所有日誌記錄嗎？')) {
            logContainer.innerHTML = '';
            // 通知伺服器清除日誌檔案
            socket.emit('clear_logs');
        }
    };

    // 同步桌面版和手機版輸入框
    function syncInputs(source, target) {
        if (source && target) {
            source.addEventListener('input', () => {
                target.value = source.value;
            });
        }
    }

    // 雙向同步輸入框
    syncInputs(urlInput, urlInputMobile);
    syncInputs(urlInputMobile, urlInput);
    syncInputs(accessCodeInput, accessCodeInputMobile);
    syncInputs(accessCodeInputMobile, accessCodeInput);
    injectScheduleLinks();

    if (scheduleGrid) {
        scheduleGrid.addEventListener('click', (event) => {
            const slotButton = event.target.closest('.schedule-slot');
            if (!slotButton || !transcriptionSchedule || !transcriptionSchedule.grid) {
                return;
            }

            const day = slotButton.dataset.day;
            const slot = Number.parseInt(slotButton.dataset.slot, 10);
            transcriptionSchedule.grid[day][slot] = !transcriptionSchedule.grid[day][slot];
            slotButton.classList.toggle('active', transcriptionSchedule.grid[day][slot]);
        });
    }

    if (scheduleEnabledInput) {
        scheduleEnabledInput.addEventListener('change', () => {
            if (!transcriptionSchedule) {
                transcriptionSchedule = buildDefaultScheduleState();
            }
            transcriptionSchedule.enabled = scheduleEnabledInput.checked;
            updateScheduleStatusUI();
        });
    }

    if (scheduleSelectAllBtn) {
        scheduleSelectAllBtn.addEventListener('click', () => setAllScheduleSlots(true));
    }

    if (scheduleClearAllBtn) {
        scheduleClearAllBtn.addEventListener('click', () => setAllScheduleSlots(false));
    }

    if (scheduleDefaultBtn) {
        scheduleDefaultBtn.addEventListener('click', applyDefaultSchedule);
    }

    if (scheduleSaveBtn) {
        scheduleSaveBtn.addEventListener('click', saveTranscriptionSchedule);
    }

    // 取消處理功能 - 現在主要用於取消當前處理中的任務
    function handleCancel() {
        if (confirm('確定要取消目前的處理任務嗎？')) {
            appendLog('🛑 使用者取消處理任務', 'info');
            socket.emit('cancel_processing');
        }
    }

    if (cancelBtn) cancelBtn.addEventListener('click', handleCancel);
    if (cancelBtnMobile) cancelBtnMobile.addEventListener('click', handleCancel);

    socket.on('connect', () => {
        const wasDisconnected = (statusBar.textContent === '與後端伺服器斷線。');
        updateStatus('已連線', false);
        if(wasDisconnected){
            appendLog('重新連接成功！', 'success');
        }

        // 定期更新 GPU 狀態（每 30 秒）
        if (window.gpuUpdateInterval) {
            clearInterval(window.gpuUpdateInterval);
        }
        window.gpuUpdateInterval = setInterval(() => {
            socket.emit('request_gpu_status');
        }, 30000); // 30 秒更新一次
    });

    socket.on('disconnect', () => {
        statusBar.textContent = '狀態：與伺服器斷線';
        statusBar.classList.remove('text-success');
        statusBar.classList.add('text-danger');
        appendLog('🔌 與後端伺服器斷線。', 'error');
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = '連線中斷';
        }
        if (submitBtnMobile) {
            submitBtnMobile.disabled = true;
            submitBtnMobile.textContent = '連線中斷';
        }
        if (cancelBtn) cancelBtn.style.display = 'none';
        if (cancelBtnMobile) cancelBtnMobile.style.display = 'none';

        videoInfoCard.style.display = 'none';

        // 清除 GPU 更新定時器
        if (window.gpuUpdateInterval) {
            clearInterval(window.gpuUpdateInterval);
            window.gpuUpdateInterval = null;
        }
    });

    socket.on('response', (msg) => {
        // Response received - no longer logging to console for production
    });

    socket.on('update_log', (data) => {
        const cleanMessage = data.log.replace(/</g, "&lt;").replace(/>/g, "&gt;");
        appendLog(cleanMessage, data.type);
    });

    // 監聽任務日誌事件（從worker傳來的日誌）
    socket.on('task_log', (data) => {
        if (data.message) {
            const cleanMessage = data.message.replace(/</g, "&lt;").replace(/>/g, "&gt;");
            appendLog(cleanMessage, 'info');
        }
    });

    socket.on('update_video_info', (data) => {
        videoTitle.textContent = data.title;
        videoUploader.textContent = data.uploader;
        if (data.thumbnail) {
            videoThumbnail.src = data.thumbnail;
        }
        const viewCount = data.view_count ? data.view_count.toLocaleString() : 'N/A';
        // 安全地設置文本內容，避免 XSS
        const safeUploadDate = (data.upload_date || '').replace(/[<>]/g, '');
        const safeDuration = (data.duration_string || '').replace(/[<>]/g, '');
        videoDetails.textContent = `${safeUploadDate} • 觀看次數：${viewCount} • 時長：${safeDuration}`;
        videoInfoCard.style.display = 'block';
    });

    socket.on('server_status_update', (data) => {
        if (data.is_busy) {
            statusBar.textContent = `狀態：伺服器忙碌中 (${data.current_task})`;
            // 不再禁用按鈕，而是改變文字提示會加入佇列
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = '加入佇列';
            }
            if (submitBtnMobile) {
                submitBtnMobile.disabled = false;
                submitBtnMobile.textContent = '加入佇列';
            }
        } else {
            statusBar.textContent = '狀態：伺服器空閒';
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = '開始處理';
            }
            if (submitBtnMobile) {
                submitBtnMobile.disabled = false;
                submitBtnMobile.textContent = '開始處理';
            }
        }
    });

    socket.on('gpu_status_update', (data) => {
        updateGPUStatus(data);
    });

    socket.on('processing_finished', () => {
        // 隱藏取消按鈕，其他狀態由 server_status_update 事件管理
        cancelBtn.style.display = 'none';
        videoInfoCard.style.display = 'none';
    });

    // 新增處理通行碼錯誤的事件
    socket.on('access_code_error', (data) => {
        // 清空通行碼輸入框，讓使用者重新輸入
        accessCodeInput.value = '';
        accessCodeInput.focus();
    });

    // 系統狀態更新函數（包含 GPU 和任務佇列資訊）
    const updateGPUStatus = (data) => {
        // 在操作日誌中顯示簡化的 GPU 資訊
        const deviceName = data.device_name || '未知設備';
        const deviceMode = data.device === 'cuda' ? 'GPU 模式' : 'CPU 模式';
        const cudaStatus = data.cuda_available ? '可用' : '不可用';

        // 獲取任務佇列資訊並更新系統資訊
        updateSystemInfo(deviceName, deviceMode, cudaStatus);
    };

    // 更新完整的系統資訊（包含 GPU 和任務佇列狀態）
    const updateSystemInfo = async (deviceName, deviceMode, cudaStatus) => {
        try {
            // 獲取任務佇列狀態
            const response = await fetch('/api/queue/status');
            const result = await response.json();

            let queueInfo = '';
            if (result.success) {
                const status = result.status;
                queueInfo = ` | 處理中: ${status.processing} | 排隊中: ${status.queued}`;
            }

            const systemInfo = `🖥️ 系統資訊 - 設備: ${deviceName} | 模式: ${deviceMode} | CUDA: ${cudaStatus}${queueInfo}`;

            // 檢查是否已經顯示過系統資訊，避免重複
            const existingSystemInfo = document.getElementById('log-container').querySelector('.system-info');
            if (existingSystemInfo) {
                existingSystemInfo.textContent = systemInfo;
            } else {
                const logEntry = document.createElement('div');
                logEntry.className = 'system-info';
                logEntry.style.color = '#0000FF';

                logEntry.textContent = systemInfo;
                document.getElementById('log-container').appendChild(logEntry);
            }
        } catch (error) {
            // 如果獲取佇列狀態失敗，只顯示 GPU 資訊
            const systemInfo = `🖥️ 系統資訊 - 設備: ${deviceName} | 模式: ${deviceMode} | CUDA: ${cudaStatus}`;

            const existingSystemInfo = document.getElementById('log-container').querySelector('.system-info');
            if (existingSystemInfo) {
                existingSystemInfo.textContent = systemInfo;
            } else {
                const logEntry = document.createElement('div');
                logEntry.className = 'system-info';
                logEntry.style.color = '#0000FF';

                logEntry.textContent = systemInfo;
                document.getElementById('log-container').appendChild(logEntry);
            }
        }
    };

    function handleFormSubmit(e) {
        e.preventDefault();
        // 獲取當前活動的輸入框值
        const url = (urlInput ? urlInput.value.trim() : '') || (urlInputMobile ? urlInputMobile.value.trim() : '');

        // 檢查是否需要通行碼
        const accessCodeDiv = document.querySelector('#access_code, #access_code_mobile');
        const isAccessCodeRequired = accessCodeDiv && !accessCodeDiv.closest('div').style.display.includes('none');
        let accessCode = '';

        if (isAccessCodeRequired) {
            accessCode = (accessCodeInput ? accessCodeInput.value.trim() : '') || (accessCodeInputMobile ? accessCodeInputMobile.value.trim() : '');
            if (!accessCode) {
                appendLog('請輸入通行碼。', 'error');
                return;
            }
        }

        if (!url) {
            appendLog('請輸入有效的音訊來源網址。', 'error');
            return;
        }

        // 同步輸入框值
        if (urlInput && urlInputMobile) {
            urlInput.value = url;
            urlInputMobile.value = url;
        }
        if (accessCodeInput && accessCodeInputMobile && accessCode) {
            accessCodeInput.value = accessCode;
            accessCodeInputMobile.value = accessCode;
        }

        if (videoInfoCard) videoInfoCard.style.display = 'none';

        socket.emit('start_processing', {
            'audio_url': url,
            'access_code': accessCode
        });

        if (transcriptionSchedule && transcriptionSchedule.enabled && !transcriptionSchedule.is_allowed_now) {
            appendLog(`Queued outside the allowed transcription schedule. Processing will start at ${formatScheduleDate(transcriptionSchedule.next_allowed_at)}.`, 'warning');
        }

        // 清空所有表單，讓用戶可以繼續添加新任務
        if (urlInput) urlInput.value = '';
        if (urlInputMobile) urlInputMobile.value = '';
        if (accessCodeInput) accessCodeInput.value = '';
        if (accessCodeInputMobile) accessCodeInputMobile.value = '';
    }

    // 綁定表單提交事件
    form.addEventListener('submit', handleFormSubmit);

    // 檔案上傳功能
    const uploadForm = document.getElementById('upload-form');
    const mediaFileInput = document.getElementById('media_file');
    const uploadAccessCodeInput = document.getElementById('upload_access_code');
    const uploadBtn = document.getElementById('upload-btn');
    const uploadBtnText = document.getElementById('upload-btn-text');
    const uploadSpinner = document.getElementById('upload-spinner');
    const uploadCancelBtn = document.getElementById('upload-cancel-btn');
    const uploadProgressContainer = document.getElementById('upload-progress-container');
    const uploadProgressBar = document.getElementById('upload-progress-bar');
    const uploadProgressText = document.getElementById('upload-progress-text');
    const uploadStatus = document.getElementById('upload-status');

    let currentUploadXHR = null;
    let currentUploadTaskId = null;

    // 檔案選擇事件
    mediaFileInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            // 檢查檔案大小
            const fileSizeMB = file.size / (1024 * 1024);
            if (fileSizeMB > 500) {
                appendLog(`⚠️ 檔案過大：${fileSizeMB.toFixed(1)}MB，建議不超過 500MB`, 'error');
            } else {
                appendLog(`📁 已選擇檔案：${file.name} (${fileSizeMB.toFixed(1)}MB)`, 'info');
            }
        }
    });

    // 上傳取消功能
    uploadCancelBtn.addEventListener('click', () => {
        if (currentUploadXHR) {
            currentUploadXHR.abort();
            appendLog('🛑 檔案上傳已取消', 'info');
            resetUploadUI();
        }
    });

    // 重置上傳介面
    function resetUploadUI() {
        uploadBtn.disabled = false;
        uploadBtnText.textContent = '上傳處理';
        uploadSpinner.style.display = 'none';
        uploadCancelBtn.style.display = 'none';
        uploadProgressContainer.style.display = 'none';
        mediaFileInput.disabled = false;
        uploadAccessCodeInput.disabled = false;
        currentUploadXHR = null;
        currentUploadTaskId = null;
    }

    // 檔案上傳表單提交
    uploadForm.addEventListener('submit', (e) => {
        e.preventDefault();

        const file = mediaFileInput.files[0];

        // 檢查是否需要通行碼
        const uploadAccessCodeDiv = document.querySelector('#upload_access_code').closest('div');
        const isUploadAccessCodeRequired = !uploadAccessCodeDiv.style.display.includes('none');
        let accessCode = '';

        if (isUploadAccessCodeRequired) {
            accessCode = uploadAccessCodeInput.value.trim();
        }

        // 驗證輸入
        if (!file) {
            appendLog('請選擇要上傳的影音檔案', 'error');
            return;
        }

        // 檢查檔案大小
        const fileSizeMB = file.size / (1024 * 1024);
        if (fileSizeMB > 500) {
            appendLog(`檔案過大：${fileSizeMB.toFixed(1)}MB，最大限制 500MB`, 'error');
            return;
        }

        // 先檢查通行碼再開始上傳
        checkAccessCodeBeforeUpload(file, accessCode);
    });

    function checkAccessCodeBeforeUpload(file, accessCode) {
        // 如果不需要通行碼，直接開始上傳
        const uploadAccessCodeDiv = document.querySelector('#upload_access_code').closest('div');
        const isUploadAccessCodeRequired = !uploadAccessCodeDiv.style.display.includes('none');
        if (!isUploadAccessCodeRequired) {
            startFileUpload(file, accessCode);
            return;
        }

        if (!accessCode) {
            appendLog('請輸入通行碼。', 'error');
            return;
        }

        appendLog('🔍 檢查通行碼...', 'info');

        // 發送一個輕量級的請求來檢查通行碼
        const xhr = new XMLHttpRequest();

        xhr.addEventListener('load', () => {
            try {
                const response = JSON.parse(xhr.responseText);

                if (xhr.status === 200 && response.success) {
                    appendLog('✅ 通行碼驗證成功', 'success');
                    // 通行碼正確，開始上傳
                    startFileUpload(file, accessCode);
                } else {
                    appendLog(`❌ 通行碼驗證失敗：${response.message || '未知錯誤'}`, 'error');
                }
            } catch (e) {
                appendLog(`❌ 驗證請求解析失敗：${e.message}`, 'error');
            }
        });

        xhr.addEventListener('error', () => {
            appendLog('❌ 網路錯誤，無法驗證通行碼', 'error');
        });

        // 發送驗證請求到系統配置狀態API（這個API也會檢查通行碼）
        const formData = new FormData();
        formData.append('access_code', accessCode);

        xhr.open('POST', '/api/verify_access_code');
        xhr.send(formData);
    }

    function startFileUpload(file, accessCode) {
        // 準備上傳界面
        uploadBtn.disabled = true;
        uploadBtnText.textContent = '上傳中...';
        uploadSpinner.style.display = 'inline-block';
        uploadCancelBtn.style.display = 'inline-block';
        uploadProgressContainer.style.display = 'block';
        mediaFileInput.disabled = true;
        uploadAccessCodeInput.disabled = true;

        // 重置進度條
        uploadProgressBar.style.width = '0%';
        uploadProgressText.textContent = '0%';
        uploadStatus.textContent = '準備上傳...';

        // 準備表單資料
        const formData = new FormData();
        formData.append('media_file', file);
        formData.append('access_code', accessCode);

        // 創建XHR請求
        const xhr = new XMLHttpRequest();
        currentUploadXHR = xhr;

        // 上傳進度監聽
        xhr.upload.addEventListener('progress', (e) => {
            if (e.lengthComputable) {
                const percentComplete = (e.loaded / e.total) * 100;
                uploadProgressBar.style.width = percentComplete + '%';
                uploadProgressText.textContent = Math.round(percentComplete) + '%';

                const uploadedMB = (e.loaded / (1024 * 1024)).toFixed(1);
                const totalMB = (e.total / (1024 * 1024)).toFixed(1);
                uploadStatus.textContent = `已上傳 ${uploadedMB}MB / ${totalMB}MB`;
            }
        });

        // 上傳完成處理
        xhr.addEventListener('load', () => {
            try {
                const response = JSON.parse(xhr.responseText);

                if (xhr.status === 200 && response.success) {
                    appendLog(`✅ 檔案上傳成功：${response.filename}`, 'success');
                    appendLog(`📝 標題：${response.title}`, 'info');
                    appendLog(`📊 檔案大小：${(response.file_size / (1024*1024)).toFixed(1)}MB`, 'info');
                    appendLog(`🎯 任務ID：${response.task_id}`, 'info');
                    if (response.queue_position > 1) {
                        appendLog(`📍 佇列位置：第${response.queue_position}位`, 'warning');
                        appendLog('📋 已加入處理佇列，請等待系統處理...', 'info');
                    } else {
                        appendLog('✅ 任務已接收並開始處理', 'success');
                    }

                    currentUploadTaskId = response.task_id;

                    // 上傳成功後隱藏進度條並重置UI
                    uploadProgressContainer.style.display = 'none';
                    uploadBtnText.textContent = '上傳處理';
                    uploadBtn.disabled = false;
                    uploadSpinner.style.display = 'none';
                    uploadCancelBtn.style.display = 'none';
                    mediaFileInput.disabled = false;
                    uploadAccessCodeInput.disabled = false;

                    // 建議用戶查看佇列頁面
                    appendLog('💡 您可以到任務佇列頁面查看處理進度', 'info');

                } else {
                    appendLog(`❌ 上傳失敗：${response.message || '未知錯誤'}`, 'error');
                    resetUploadUI();
                }
            } catch (e) {
                appendLog(`❌ 解析回應失敗：${e.message}`, 'error');
                resetUploadUI();
            }
        });

        // 上傳錯誤處理
        xhr.addEventListener('error', () => {
            appendLog('❌ 網路錯誤，上傳失敗', 'error');
            resetUploadUI();
        });

        // 上傳中止處理
        xhr.addEventListener('abort', () => {
            appendLog('🛑 上傳已取消', 'info');
            resetUploadUI();
        });

        // 發送請求
        uploadStatus.textContent = '連線中...';
        xhr.open('POST', '/api/upload_media');
        xhr.send(formData);

        appendLog(`📤 開始上傳檔案：${file.name}`, 'info');
    }

    // 監聽處理完成事件（包含上傳任務）
    socket.on('processing_finished', () => {
        // 隱藏取消按鈕，其他狀態由 server_status_update 事件管理
        cancelBtn.style.display = 'none';
        videoInfoCard.style.display = 'none';

        // 重置上傳表單
        if (currentUploadTaskId) {
            appendLog('✅ 上傳檔案處理完成', 'success');
            resetUploadUI();

            // 清空表單
            uploadForm.reset();
        }
    });
    loadTranscriptionSchedule();
});
