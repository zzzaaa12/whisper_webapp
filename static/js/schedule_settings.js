document.addEventListener('DOMContentLoaded', () => {
    const scheduleDays = document.getElementById('schedule-days');
    const scheduleEnabledInput = document.getElementById('schedule-enabled');
    const scheduleStatusText = document.getElementById('schedule-status-text');
    const scheduleNextAllowed = document.getElementById('schedule-next-allowed');
    const scheduleTimezone = document.getElementById('schedule-timezone');
    const scheduleSaveBtn = document.getElementById('schedule-save-btn');
    const scheduleDefaultBtn = document.getElementById('schedule-default-btn');
    const scheduleAccessCode = document.getElementById('schedule-access-code');
    const scheduleMessage = document.getElementById('schedule-message');
    const weekdayLabels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    const timeOptions = Array.from({ length: 48 }, (_, index) => {
        const hour = String(Math.floor(index / 2)).padStart(2, '0');
        const minute = index % 2 === 0 ? '00' : '30';
        return `${hour}:${minute}`;
    });
    let transcriptionSchedule = null;

    function setMessage(message, type = 'secondary') {
        if (!scheduleMessage) {
            return;
        }
        scheduleMessage.className = `alert alert-${type} mb-3`;
        scheduleMessage.textContent = message;
        scheduleMessage.style.display = 'block';
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
        if (!transcriptionSchedule) {
            return;
        }

        const enabled = Boolean(transcriptionSchedule.enabled);
        const isAllowedNow = Boolean(transcriptionSchedule.is_allowed_now);
        scheduleEnabledInput.checked = enabled;
        scheduleTimezone.textContent = transcriptionSchedule.timezone || 'Asia/Taipei';
        scheduleStatusText.textContent = !enabled ? 'Schedule disabled' : (isAllowedNow ? 'Allowed now' : 'Blocked now');
        scheduleNextAllowed.textContent = formatScheduleDate(transcriptionSchedule.next_allowed_at);
    }

    function createDefaultRanges() {
        return [
            { start: '00:00', end: '08:00' },
            { start: '12:30', end: '13:30' },
            { start: '18:30', end: '20:00' }
        ];
    }

    function createDefaultScheduleState() {
        const days = {};
        for (let day = 0; day < 7; day += 1) {
            days[String(day)] = createDefaultRanges().map((range) => ({ ...range }));
        }

        return {
            enabled: true,
            timezone: 'Asia/Taipei',
            apply_to_task_types: ['youtube', 'upload_media'],
            days,
            is_allowed_now: false,
            next_allowed_at: null
        };
    }

    function normalizeScheduleState(source) {
        const fallback = createDefaultScheduleState();
        const weekdays = source && source.weekdays ? source.weekdays : {};
        const days = {};

        for (let day = 0; day < 7; day += 1) {
            const key = String(day);
            const ranges = Array.isArray(weekdays[key]) ? weekdays[key] : [];
            days[key] = ranges
                .filter((value) => typeof value === 'string' && value.includes('-'))
                .map((value) => {
                    const [start, end] = value.split('-', 2);
                    return { start, end };
                });
        }

        return {
            enabled: source ? Boolean(source.enabled) : fallback.enabled,
            timezone: source && source.timezone ? source.timezone : fallback.timezone,
            apply_to_task_types: source && Array.isArray(source.apply_to_task_types) ? source.apply_to_task_types : fallback.apply_to_task_types,
            days,
            is_allowed_now: source ? Boolean(source.is_allowed_now) : fallback.is_allowed_now,
            next_allowed_at: source ? source.next_allowed_at : fallback.next_allowed_at
        };
    }

    function rangesToTimelineBlocks(ranges) {
        return ranges.map((range) => {
            const startIndex = timeOptions.indexOf(range.start);
            const endIndex = timeOptions.indexOf(range.end);
            const safeStart = Math.max(0, startIndex);
            const safeEnd = endIndex === -1 ? 48 : endIndex;
            return {
                left: `${(safeStart / 48) * 100}%`,
                width: `${Math.max(0, safeEnd - safeStart) / 48 * 100}%`
            };
        });
    }

    function rangesToGrid(ranges) {
        const slots = Array(48).fill(false);
        ranges.forEach((range) => {
            const startIndex = timeOptions.indexOf(range.start);
            const endIndex = range.end === '24:00' ? 48 : timeOptions.indexOf(range.end);
            if (startIndex === -1 || endIndex === -1 || startIndex >= endIndex) {
                return;
            }
            for (let slot = startIndex; slot < endIndex; slot += 1) {
                slots[slot] = true;
            }
        });
        return slots;
    }

    function createTimeSelect(selectedValue) {
        const select = document.createElement('select');
        select.className = 'form-select form-select-sm';
        timeOptions.concat('24:00').forEach((time) => {
            if (time === '24:00' || timeOptions.includes(time)) {
                const option = document.createElement('option');
                option.value = time;
                option.textContent = time;
                option.selected = time === selectedValue;
                select.appendChild(option);
            }
        });
        return select;
    }

    function renderScheduleEditor() {
        if (!scheduleDays || !transcriptionSchedule) {
            return;
        }

        scheduleDays.innerHTML = '';

        weekdayLabels.forEach((label, dayIndex) => {
            const dayKey = String(dayIndex);
            const dayRanges = transcriptionSchedule.days[dayKey] || [];
            const card = document.createElement('div');
            card.className = 'schedule-day-card mb-3';

            const header = document.createElement('div');
            header.className = 'schedule-day-head';
            header.innerHTML = `
                <div>
                    <h2 class="schedule-day-title">${label}</h2>
                    <div class="text-muted small">Add one or more allowed time ranges. Half-hour increments only.</div>
                </div>
            `;

            const addButton = document.createElement('button');
            addButton.type = 'button';
            addButton.className = 'btn btn-outline-primary btn-sm';
            addButton.textContent = 'Add range';
            addButton.dataset.day = dayKey;
            header.appendChild(addButton);
            card.appendChild(header);

            const timeline = document.createElement('div');
            timeline.className = 'schedule-timeline';
            rangesToTimelineBlocks(dayRanges).forEach((block) => {
                const element = document.createElement('div');
                element.className = 'schedule-block';
                element.style.left = block.left;
                element.style.width = block.width;
                timeline.appendChild(element);
            });
            card.appendChild(timeline);

            const hours = document.createElement('div');
            hours.className = 'schedule-hours';
            hours.innerHTML = '<span>00:00</span><span>04:00</span><span>08:00</span><span>12:00</span><span>16:00</span><span>20:00</span>';
            card.appendChild(hours);

            if (dayRanges.length === 0) {
                const empty = document.createElement('div');
                empty.className = 'empty-range';
                empty.textContent = 'No allowed ranges for this day.';
                card.appendChild(empty);
            } else {
                const list = document.createElement('div');
                list.className = 'range-list';

                dayRanges.forEach((range, rangeIndex) => {
                    const row = document.createElement('div');
                    row.className = 'range-row';
                    row.dataset.day = dayKey;
                    row.dataset.index = String(rangeIndex);

                    const startSelect = createTimeSelect(range.start);
                    startSelect.dataset.role = 'start';

                    const endSelect = createTimeSelect(range.end);
                    endSelect.dataset.role = 'end';

                    const arrow = document.createElement('div');
                    arrow.className = 'range-arrow';
                    arrow.textContent = 'to';

                    const removeButton = document.createElement('button');
                    removeButton.type = 'button';
                    removeButton.className = 'btn btn-outline-danger btn-sm';
                    removeButton.textContent = 'Delete';
                    removeButton.dataset.action = 'delete-range';

                    row.appendChild(startSelect);
                    row.appendChild(arrow);
                    row.appendChild(endSelect);
                    row.appendChild(removeButton);
                    list.appendChild(row);
                });

                card.appendChild(list);
            }

            scheduleDays.appendChild(card);
        });

        updateScheduleStatusUI();
    }

    async function loadTranscriptionSchedule() {
        try {
            const response = await fetch('/api/system/transcription-schedule');
            const result = await response.json();
            if (!result.success) {
                throw new Error(result.message || 'Unable to load transcription schedule.');
            }

            transcriptionSchedule = normalizeScheduleState(result.schedule);
            renderScheduleEditor();
        } catch (error) {
            transcriptionSchedule = createDefaultScheduleState();
            renderScheduleEditor();
            setMessage(`Failed to load transcription schedule: ${error.message}`, 'danger');
        }
    }

    function applyDefaultSchedule() {
        transcriptionSchedule = createDefaultScheduleState();
        renderScheduleEditor();
        setMessage('Default schedule applied. Save to persist the change.', 'secondary');
    }

    function validateRanges() {
        for (let day = 0; day < 7; day += 1) {
            const dayRanges = transcriptionSchedule.days[String(day)] || [];
            for (const range of dayRanges) {
                if (!range.start || !range.end) {
                    throw new Error('Every range must have a start and end time.');
                }
                const startIndex = timeOptions.indexOf(range.start);
                const endIndex = range.end === '24:00' ? 48 : timeOptions.indexOf(range.end);
                if (startIndex === -1 || endIndex === -1 || startIndex >= endIndex) {
                    throw new Error('Each range must end after it starts.');
                }
            }
        }
    }

    async function saveTranscriptionSchedule() {
        if (!transcriptionSchedule) {
            return;
        }

        try {
            validateRanges();
        } catch (error) {
            setMessage(error.message, 'danger');
            return;
        }

        const weekdays = {};
        Object.keys(transcriptionSchedule.days).forEach((day) => {
            weekdays[day] = rangesToGrid(transcriptionSchedule.days[day]);
        });

        const payload = {
            access_code: scheduleAccessCode ? scheduleAccessCode.value.trim() : '',
            schedule: {
                enabled: scheduleEnabledInput.checked,
                timezone: transcriptionSchedule.timezone || 'Asia/Taipei',
                apply_to_task_types: transcriptionSchedule.apply_to_task_types || ['youtube', 'upload_media'],
                weekdays
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

            transcriptionSchedule = normalizeScheduleState(result.schedule);
            renderScheduleEditor();
            setMessage('Transcription schedule saved.', 'success');
        } catch (error) {
            setMessage(`Failed to save transcription schedule: ${error.message}`, 'danger');
        } finally {
            scheduleSaveBtn.disabled = false;
        }
    }

    scheduleEnabledInput.addEventListener('change', () => {
        if (!transcriptionSchedule) {
            transcriptionSchedule = createDefaultScheduleState();
        }
        transcriptionSchedule.enabled = scheduleEnabledInput.checked;
        updateScheduleStatusUI();
    });

    scheduleDays.addEventListener('click', (event) => {
        const addButton = event.target.closest('.schedule-day-head .btn');
        if (addButton) {
            const day = addButton.dataset.day;
            transcriptionSchedule.days[day].push({ start: '00:00', end: '00:30' });
            renderScheduleEditor();
            return;
        }

        const deleteButton = event.target.closest('[data-action="delete-range"]');
        if (deleteButton) {
            const row = deleteButton.closest('.range-row');
            const day = row.dataset.day;
            const index = Number.parseInt(row.dataset.index, 10);
            transcriptionSchedule.days[day].splice(index, 1);
            renderScheduleEditor();
        }
    });

    scheduleDays.addEventListener('change', (event) => {
        const row = event.target.closest('.range-row');
        if (!row) {
            return;
        }

        const day = row.dataset.day;
        const index = Number.parseInt(row.dataset.index, 10);
        const role = event.target.dataset.role;
        transcriptionSchedule.days[day][index][role] = event.target.value;
        renderScheduleEditor();
    });

    scheduleDefaultBtn.addEventListener('click', applyDefaultSchedule);
    scheduleSaveBtn.addEventListener('click', saveTranscriptionSchedule);

    loadTranscriptionSchedule();
});
