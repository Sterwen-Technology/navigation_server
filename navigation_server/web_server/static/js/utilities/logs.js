import {
  apiPost
} from '../api.js';
import {
  activeWindows, createWindow, windowKey
} from '../windows.js';
import {
  t
} from '../translations-bridge.js';

export { appendLogLineForWindow };
export { clearLogForWindow };
export { closeLog };
export { openLog };
export { startLogStreamForWindow };
export { stopLogStreamForWindow };

function openLog(processName) {
    const key = windowKey('log', processName);
    const existing = activeWindows.get(key);
    
    if (existing) {
        // Bring existing window to front
        existing.element.style.zIndex = ++windowZIndex;
        return;
    }

    const win = createWindow('log', processName, `Logs — ${processName}`, (win) => {
        // Cleanup when window closes
        stopLogStreamForWindow(win);
    });
    
    // Set larger default size for log windows
    win.element.style.width = '800px';
    win.element.style.height = '600px';

    // Create log window content
    const content = document.createElement('div');
    content.style.display = 'flex';
    content.style.flexDirection = 'column';
    content.style.height = '100%';
    content.style.gap = '12px';

    // Create controls
    const controls = document.createElement('div');
    controls.style.display = 'flex';
    controls.style.gap = '8px';
    controls.style.flexWrap = 'wrap';

    const startBtn = document.createElement('button');
    startBtn.textContent = '▶ Start';
    startBtn.title = 'Start';
    startBtn.id = `log-start-btn-${win.processName}`;

    const stopBtn = document.createElement('button');
    stopBtn.textContent = '■ Stop';
    stopBtn.title = 'Stop';
    stopBtn.disabled = true;
    stopBtn.id = `log-stop-btn-${win.processName}`;

    const clearBtn = document.createElement('button');
    clearBtn.textContent = '✓ Clear';
    clearBtn.title = 'Clear';
    clearBtn.id = `log-clear-btn-${win.processName}`;

    controls.appendChild(startBtn);
    controls.appendChild(stopBtn);
    controls.appendChild(clearBtn);

    // Create log body
    const logBody = document.createElement('div');
    logBody.className = 'log-content';
    logBody.id = `log-body-${win.processName}`;
    logBody.textContent = 'Click Start to start the log stream...';
    logBody.style.flex = '1';
    logBody.style.overflowY = 'auto';

    content.appendChild(controls);
    content.appendChild(logBody);

    win.body.appendChild(content);
    win.body.style.overflow = 'hidden';
    win.body.style.display = 'flex';
    win.body.style.flexDirection = 'column';

    // Store window-specific state
    win.logProcess = win.processName;
    win.logEventSource = null;

    // Setup button handlers
    startBtn.addEventListener('click', () => startLogStreamForWindow(win));
    stopBtn.addEventListener('click', () => stopLogStreamForWindow(win));
    clearBtn.addEventListener('click', () => clearLogForWindow(win));

    // Auto-start the stream
    startLogStreamForWindow(win);
}

function startLogStreamForWindow(win) {
    if (!win.logProcess) return;
    
    // Stop any existing stream
    if (win.logEventSource) {
        win.logEventSource.close();
        win.logEventSource = null;
    }

    const startBtn = document.getElementById(`log-start-btn-${win.processName}`);
    const stopBtn = document.getElementById(`log-stop-btn-${win.processName}`);
    
    if (startBtn) startBtn.disabled = true;
    if (stopBtn) stopBtn.disabled = false;

    win.logEventSource = new EventSource(`/api/log/stream/${encodeURIComponent(win.logProcess)}`);
    
    win.logEventSource.addEventListener("started", () => {
        appendLogLineForWindow(win, t.t("console.stream_started"));
    });
    
    win.logEventSource.addEventListener("error", (e) => {
        if (e.data) appendLogLineForWindow(win, "ERREUR: " + e.data);
        stopLogStreamForWindow(win);
    });
    
    win.logEventSource.onmessage = (e) => {
        appendLogLineForWindow(win, e.data);
    };
}

async function stopLogStreamForWindow(win) {
    if (win.logEventSource) {
        win.logEventSource.close();
        win.logEventSource = null;
    }

    const startBtn = document.getElementById(`log-start-btn-${win.processName}`);
    const stopBtn = document.getElementById(`log-stop-btn-${win.processName}`);
    
    if (startBtn) startBtn.disabled = false;
    if (stopBtn) stopBtn.disabled = true;
    
    appendLogLineForWindow(win, t.t("console.stream_stopped"));
    try {
        await apiPost(`/api/log/stop/${encodeURIComponent(win.logProcess)}`, {});
    } catch (e) { /* ignore */ }
}

function appendLogLineForWindow(win, line) {
    const logBody = document.getElementById(`log-body-${win.processName}`);
    if (logBody) {
        logBody.textContent += line + "\n";
        logBody.scrollTop = logBody.scrollHeight;
    }
}

function clearLogForWindow(win) {
    const logBody = document.getElementById(`log-body-${win.processName}`);
    if (logBody) {
        logBody.textContent = "";
    }
}

function closeLog() {
    // This function is kept for backward compatibility but is no longer used
    // since we're using createWindow system now
}

