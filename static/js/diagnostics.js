(function () {
    'use strict';

    const endpoint = '/api/client-diagnostics';
    const maxReports = 30;
    let reportCount = 0;

    function compact(value, limit) {
        const text = String(value == null ? '' : value);
        return text.length > limit ? text.slice(0, limit) + '…' : text;
    }

    function report(type, details) {
        if (reportCount >= maxReports) return;
        reportCount += 1;
        const payload = Object.assign({
            type: type,
            page: location.pathname,
            timestamp: new Date().toISOString()
        }, details || {});
        Object.keys(payload).forEach(key => {
            if (typeof payload[key] === 'string') payload[key] = compact(payload[key], key === 'stack' ? 2000 : 500);
        });

        try {
            const body = JSON.stringify(payload);
            if (navigator.sendBeacon) {
                navigator.sendBeacon(endpoint, new Blob([body], {type: 'application/json'}));
            } else {
                window.fetch(endpoint, {method: 'POST', headers: {'Content-Type': 'application/json'}, body, keepalive: true});
            }
        } catch (_) {
            // Diagnostics must never interfere with the application.
        }
    }

    window.addEventListener('error', event => {
        report('javascript-error', {
            message: event.message,
            source: event.filename,
            line: event.lineno,
            column: event.colno,
            stack: event.error && event.error.stack
        });
    });

    window.addEventListener('unhandledrejection', event => {
        const reason = event.reason;
        report('unhandled-rejection', {
            message: reason && reason.message ? reason.message : reason,
            stack: reason && reason.stack
        });
    });

    const originalFetch = window.fetch.bind(window);
    window.fetch = function (input, options) {
        const url = typeof input === 'string' ? input : input && input.url;
        if (url && url.includes(endpoint)) return originalFetch(input, options);

        const started = performance.now();
        let completed = false;
        const pendingTimer = setTimeout(() => {
            if (!completed) report('fetch-pending', {url, duration_ms: Math.round(performance.now() - started)});
        }, 3000);

        return originalFetch(input, options).then(response => {
            const duration = Math.round(performance.now() - started);
            if (!response.ok || duration >= 1000) {
                report('fetch-complete', {url, status: response.status, duration_ms: duration});
            }
            return response;
        }).catch(error => {
            report('fetch-error', {url, message: error.message, stack: error.stack, duration_ms: Math.round(performance.now() - started)});
            throw error;
        }).finally(() => {
            completed = true;
            clearTimeout(pendingTimer);
        });
    };

    let heartbeat = performance.now();
    setInterval(() => {
        const now = performance.now();
        const drift = now - heartbeat - 1000;
        if (drift >= 2000) report('event-loop-stall', {duration_ms: Math.round(drift)});
        heartbeat = now;
    }, 1000);

    if ('PerformanceObserver' in window) {
        try {
            new PerformanceObserver(list => {
                list.getEntries().forEach(entry => {
                    if (entry.duration >= 250) report('long-task', {duration_ms: Math.round(entry.duration)});
                });
            }).observe({entryTypes: ['longtask']});
        } catch (_) {
            // Long-task observation is not available in every browser.
        }
    }
})();
