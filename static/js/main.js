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

    // 取消處理功能 - 現在主要用於取消當前處理中的任務
    cancelBtn.addEventListener('click', () => {
        if (confirm('確定要取消目前的處理任務嗎？')) {
            appendLog('🛑 使用者取消處理任務', 'info');
            socket.emit('cancel_processing');
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
        submitBtn.textContent = '連線中斷';
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
        // Response received - no longer logging to console for production
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
            submitBtn.disabled = false;
            submitBtn.textContent = '加入佇列';
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
            existingGpuInfo.textContent = gpuInfo;
        } else {
            const logEntry = document.createElement('div');
            logEntry.className = 'gpu-info';
            logEntry.style.color = '#0000FF';

            logEntry.textContent = gpuInfo;
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

        videoInfoCard.style.display = 'none';
        appendLog(`收到請求，準備處理網址: ${url}`);

        socket.emit('start_processing', {
            'audio_url': url,
            'access_code': accessCode
        });

        // 清空表單，讓用戶可以繼續添加新任務
        urlInput.value = '';
        accessCodeInput.value = '';
    });

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
        const accessCode = uploadAccessCodeInput.value.trim();

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
                    appendLog('💡 您可以到 <a href="/queue" target="_blank">任務佇列頁面</a> 查看處理進度', 'info');

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

});