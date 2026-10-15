import { $ } from './config.js';


export { activeWindows };
export { closeWindow };
export { createWindow };
export { focusWindow };
export { makeDraggable };
export { makeResizable };
export { minimizeWindow };
export { toast };
export { windowKey };


// Window Management System
let windowZIndex = 1000;
let activeWindows = new Map(); // windowKey -> {element, body, header, processName, serviceType, cleanup}
let isDragging = null;
let dragOffset = {x: 0, y: 0};
let nextWindowPos = {x: 80, y: 80};


const $ = (id) => document.getElementById(id);

function windowKey(serviceType, processName) {
    return `${serviceType}:${processName}`;
}

// Window Management Functions
// If a single-instance window for (serviceType, processName) is already
// open, bring it to the front and return its record; otherwise null.
function focusWindow(serviceType, processName) {
    const key = windowKey(serviceType, processName);
    const win = activeWindows.get(key);
    if (win) {
        win.element.style.zIndex = ++windowZIndex;
        return win;
    }
    return null;
}

// Creates an independent, draggable service window. Only one window per
// (serviceType, processName) exists at a time: calling createWindow again
// for an open service reuses that window. `onClose` (optional) is invoked
// when the window closes so callers stop refresh timers.
function createWindow(serviceType, processName, title, onClose) {
    const existing = focusWindow(serviceType, processName);
    if (existing) {
        existing.headerTitle.textContent = title;
        return existing;
    }

    const key = windowKey(serviceType, processName);
    const windowEl = document.createElement('div');
    windowEl.className = 'service-window';
    const pos = nextWindowPos;
    windowEl.style.left = pos.x + 'px';
    windowEl.style.top = pos.y + 'px';
    windowEl.style.width = '520px';
    windowEl.style.zIndex = ++windowZIndex;
    pos.x = (pos.x + 28) % (window.innerWidth - 560);
    pos.y = (pos.y + 28) % (window.innerHeight - 260);

    const headerEl = document.createElement('div');
    headerEl.className = 'window-header';
    headerEl.innerHTML = `
        <div class="window-title-bar">
            <h2></h2>
        </div>
        <div class="window-controls">
            <button class="window-btn minimize" title="Minimize"></button>
            <button class="window-btn close" title="Close"></button>
        </div>
    `;
    const headerTitle = headerEl.querySelector('h2');
    headerTitle.textContent = title;

    const bodyEl = document.createElement('div');
    bodyEl.className = 'window-body';

    const resizeHandle = document.createElement('div');
    resizeHandle.className = 'window-resize-handle';

    windowEl.appendChild(headerEl);
    windowEl.appendChild(bodyEl);
    windowEl.appendChild(resizeHandle);
    $("window-container").appendChild(windowEl);

    const record = {
        element: windowEl,
        body: bodyEl,
        header: headerEl,
        headerTitle: headerTitle,
        processName: processName,
        serviceType: serviceType,
        cleanup: null,
        _onClose: onClose || null
    };

    headerEl.querySelector('.window-btn.minimize').addEventListener('click', (e) => {
        e.stopPropagation();
        minimizeWindow(key);
    });
    headerEl.querySelector('.window-btn.close').addEventListener('click', (e) => {
        e.stopPropagation();
        closeWindow(key);
    });

    windowEl.addEventListener('mousedown', () => {
        windowEl.style.zIndex = ++windowZIndex;
    });

    makeDraggable(windowEl, headerEl);
    makeResizable(windowEl, resizeHandle);

    activeWindows.set(key, record);
    return record;
}

function closeWindow(key) {
    const win = activeWindows.get(key);
    if (!win) return;
    if (win._onClose) {
        try { win._onClose(win); } catch (e) { console.error('window cleanup error', e); }
    }
    if (win.cleanup) {
        try { win.cleanup(); } catch (e) { console.error('window cleanup error', e); }
    }
    win.element.remove();
    activeWindows.delete(key);
}

function minimizeWindow(key) {
    const win = activeWindows.get(key);
    if (!win) return;
    const body = win.body;
    body.style.display = body.style.display === 'none' ? '' : 'none';
}

function makeDraggable(element, handle) {
    handle.addEventListener('mousedown', (e) => {
        if (e.target.classList.contains('window-btn') || e.target.tagName === 'BUTTON') {
            return; // Don't drag when clicking buttons
        }
        isDragging = element;
        dragOffset.x = e.clientX - element.getBoundingClientRect().left;
        dragOffset.y = e.clientY - element.getBoundingClientRect().top;
        element.style.cursor = 'move';
        e.preventDefault();
    });
}

function makeResizable(element, handle) {
    let resizing = null;
    let start = {x: 0, y: 0, w: 0, h: 0};
    const onMove = (e) => {
        if (!resizing) return;
        resizing.style.width = Math.max(300, start.w + (e.clientX - start.x)) + 'px';
        resizing.style.height = Math.max(200, start.h + (e.clientY - start.y)) + 'px';
    };
    const onUp = () => {
        if (!resizing) return;
        resizing = null;
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
    };
    handle.addEventListener('mousedown', (e) => {
        e.preventDefault();
        e.stopPropagation();
        resizing = element;
        const rect = element.getBoundingClientRect();
        start = {x: e.clientX, y: e.clientY, w: rect.width, h: rect.height};
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
    });
}

document.addEventListener('mousemove', (e) => {
    if (isDragging) {
        isDragging.style.left = (e.clientX - dragOffset.x) + 'px';
        isDragging.style.top = (e.clientY - dragOffset.y) + 'px';
    }
});

document.addEventListener('mouseup', () => {
    if (isDragging) {
        isDragging.style.cursor = '';
        isDragging = null;
    }
});

function toast(msg, ok = true) {
    const toastEl = $("toast");
    toastEl.textContent = msg;
    toastEl.className = "toast show " + (ok ? "ok" : "err");
    setTimeout(() => toastEl.classList.remove("show"), 3500);
}

