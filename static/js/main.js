document.addEventListener('DOMContentLoaded', () => {

    const socket = io();

    const form = document.getElementById('process-form');
    const urlInput = document.getElementById('audio_url');
    const accessCodeInput = document.getElementById('access_code');
    const submitBtn = document.getElementById('submit-btn');
    const cancelBtn = document.getElementById('cancel-btn');
    const logContainer = document.getElementById('log-container');
    const statusBar = document.getElementById('status-footer');
    const videoInfoCard = document.getElementById('video-info-card');
    const videoThumbnail = document.getElementById('video-thumbnail');
    const videoTitle = document.getElementById('video-title');
    const videoUploader = document.getElementById('video-uploader');
    const videoDetails = document.getElementById('video-details');

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

        logEntry.innerHTML = `[${timestamp}] ${message}`;
        if(colorClass) {
            logEntry.classList.add(colorClass);
        }

        logContainer.appendChild(logEntry);

        // 智能滾動：如果使用者沒有手動滾動，則自動滾動到底部
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

    // 取消處理功能
    cancelBtn.addEventListener('click', () => {
        if (confirm('確定要取消目前的處理任務嗎？')) {
            appendLog('🛑 使用者取消處理任務', 'info');
            socket.emit('cancel_processing');

            // 重置按鈕狀態
            submitBtn.disabled = false;
            submitBtn.textContent = '開始處理';
            urlInput.disabled = false;
            accessCodeInput.disabled = false;
            cancelBtn.style.display = 'none';

            // 隱藏影片資訊
            videoInfoCard.style.display = 'none';
        }
    });

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
        submitBtn.disabled = true;
        submitBtn.textContent = '伺服器忙碌中';
        accessCodeInput.disabled = true;
        cancelBtn.style.display = 'none';

        videoInfoCard.style.display = 'none';

        // 清除 GPU 更新定時器
        if (window.gpuUpdateInterval) {
            clearInterval(window.gpuUpdateInterval);
            window.gpuUpdateInterval = null;
        }
    });

    socket.on('response', (msg) => {
        console.log('Received response:', msg);
    });

    socket.on('update_log', (data) => {
        const cleanMessage = data.log.replace(/</g, "&lt;").replace(/>/g, "&gt;");
        appendLog(cleanMessage, data.type);
    });

    socket.on('update_video_info', (data) => {
        videoTitle.textContent = data.title;
        videoUploader.textContent = data.uploader;
        if (data.thumbnail) {
            videoThumbnail.src = data.thumbnail;
        }
        const viewCount = data.view_count ? data.view_count.toLocaleString() : 'N/A';
        videoDetails.innerHTML = `
            ${data.upload_date} &bull;
            觀看次數：${viewCount} &bull;
            時長：${data.duration_string}
        `;
        videoInfoCard.style.display = 'block';
    });

    socket.on('server_status_update', (data) => {
        if (data.is_busy) {
            statusBar.textContent = `狀態：伺服器忙碌中 (${data.current_task})`;
            submitBtn.disabled = true;
            submitBtn.textContent = '伺服器忙碌中';
        } else {
            statusBar.textContent = '狀態：伺服器空閒';
            submitBtn.disabled = false;
            submitBtn.textContent = '開始處理';
        }
    });

    socket.on('gpu_status_update', (data) => {
        updateGPUStatus(data);
    });

    socket.on('processing_finished', () => {
        submitBtn.disabled = false;
        submitBtn.textContent = '開始處理';
        urlInput.disabled = false;
        accessCodeInput.disabled = false;
        cancelBtn.style.display = 'none';
    });

    // 新增處理通行碼錯誤的事件
    socket.on('access_code_error', (data) => {
        // 重新啟用輸入框，讓使用者可以重新輸入通行碼
        submitBtn.disabled = false;
        submitBtn.textContent = '開始處理';
        urlInput.disabled = false;
        // accessCodeInput.disabled = true; // 移除這行，保持通行碼輸入框可輸入
        cancelBtn.style.display = 'none';

        // 清空通行碼輸入框，讓使用者重新輸入
        accessCodeInput.value = '';
        accessCodeInput.focus();
    });

    // GPU 狀態更新函數（簡化版）
    const updateGPUStatus = (data) => {
        // 在操作日誌中顯示簡化的 GPU 資訊
        const deviceName = data.device_name || '未知設備';
        const deviceMode = data.device === 'cuda' ? 'GPU 模式' : 'CPU 模式';
        const cudaStatus = data.cuda_available ? '可用' : '不可用';

        const gpuInfo = `🖥️ 系統資訊 - 設備: ${deviceName} | 模式: ${deviceMode} | CUDA: ${cudaStatus}`;

        // 檢查是否已經顯示過 GPU 資訊，避免重複
        const existingGpuInfo = logContainer.querySelector('.gpu-info');
        if (existingGpuInfo) {
            existingGpuInfo.innerHTML = gpuInfo;
        } else {
            const logEntry = document.createElement('div');
            logEntry.className = 'gpu-info';
            logEntry.style.color = '#0000FF';

            logEntry.innerHTML = gpuInfo;
            logContainer.appendChild(logEntry);
        }
    };

    form.addEventListener('submit', (e) => {
        e.preventDefault();
        const url = urlInput.value.trim();
        const accessCode = accessCodeInput.value.trim();

        if (!url) {
            appendLog('請輸入有效的音訊來源網址。', 'error');
            return;
        }
        if (!accessCode) {
            appendLog('請輸入通行碼。', 'error');
            return;
        }

        // 只禁用提交按鈕和 URL 輸入框，保持通行碼輸入框可輸入
        submitBtn.disabled = true;
        urlInput.disabled = true;
        // accessCodeInput.disabled = true; // 移除這行，保持通行碼輸入框可輸入
        cancelBtn.style.display = 'inline-block';

        videoInfoCard.style.display = 'none';

        appendLog(`收到請求，準備處理網址: ${url}`);

        socket.emit('start_processing', {
            'audio_url': url,
            'access_code': accessCode
        });
    });

});