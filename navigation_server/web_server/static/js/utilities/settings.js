import { apiGet, apiPost } from '../api.js';
import { escapeHtml } from '../common.js';
import { $ } from '../config.js';
import { translateAllElements } from '../i18n.js';
import { activeWindows, closeWindow, createWindow, toast, windowKey } from '../windows.js';
import { t } from '../translations-bridge.js';

export { closeSettingsWindow };
export { loadJsYaml };
export { refreshSettings };
export { renderSettings };
export { saveSettings };
export { setupYamlValidation };
export { showSettings };
export { simpleYamlValidation };
export { validateYamlSyntax };

async function showSettings(target) {
    const win = createWindow('settings', target, `Settings — ${target}`, (w) => {
        if (w.timer) { clearTimeout(w.timer); w.timer = null; }
    });
    win.target = target;
    win.body.innerHTML = `<div class="empty">${t.t("general.loading")}</div>`;
    await refreshSettings(win);
}

async function refreshSettings(win) {
    if (!win || activeWindows.get(windowKey('settings', win.target)) !== win) return;
    const target = win.target;
    try {
        const r = await apiGet(`/api/settings/${encodeURIComponent(target)}`);
        if (activeWindows.get(windowKey('settings', target)) === win) {
            renderSettings(r, target, win.body, win);
        }
    } catch (e) {
        if (activeWindows.get(windowKey('settings', target)) === win) {
            win.body.innerHTML = `<div class="empty">Error: ${escapeHtml(e.message)}</div>`;
        }
    }
}

function renderSettings(data, target, body, win) {
    if (!data.ok) {
        body.innerHTML = `<div class="empty">${escapeHtml(data.error || "Error loading settings")}</div>`;
        t.translateAllElements();
        return;
    }
    
    // Create an editable YAML editor
    const settingsContent = data.settings_content || '';
    const settingsFile = escapeHtml(data.settings_file || '');
    const escapedContent = escapeHtml(settingsContent);
    
    body.innerHTML = `
        <div class="settings-header">
            <strong>File:</strong> ${settingsFile}
            <div class="settings-actions" style="margin-top: 8px;">
                <button class="open-btn" onclick="saveSettings('${target}', this)" title="Save changes">✓ Save</button>
                <button onclick="closeSettingsWindow('${target}')" title="Close">✕ Close</button>
            </div>
        </div>
        <div class="settings-content">
            <div class="settings-editor-container">
                <div id="settings-codemirror-${target}" class="yaml-editor"></div>
            </div>
            <div id="yaml-error-${target}" class="yaml-error" style="display:none;"></div>
        </div>
    `;
    t.translateAllElements();
    
    // Initialize CodeMirror editor if available
    if (typeof CodeMirror !== 'undefined') {
        const editorElement = document.getElementById(`settings-codemirror-${target}`);
        if (editorElement) {
            win.codemirrorEditor = CodeMirror(editorElement, {
                value: settingsContent,
                mode: 'yaml',
                theme: 'dracula',
                lineNumbers: true,
                lineWrapping: true,
                indentUnit: 2,
                tabSize: 2,
                spellcheck: false,
                autofocus: true
            });
        }
    }
    
    // Store the original content for comparison
    if (win) {
        win.originalContent = settingsContent;
    }
    
    // Add YAML validation on the fly (if available)
    setupYamlValidation(target);
}

function closeSettingsWindow(target) {
    const key = windowKey('settings', target);
    closeWindow(key);
}

async function saveSettings(target, button) {
    const win = activeWindows.get(windowKey('settings', target));
    if (!win) return;
    
    let content = '';
    
    // Try to get content from CodeMirror first, fallback to textarea
    if (win.codemirrorEditor) {
        content = win.codemirrorEditor.getValue();
    } else {
        const textarea = $(`settings-textarea-${target}`);
        if (!textarea) return;
        content = textarea.value;
    }
    
    // Validate YAML syntax first
    const errorElement = $(`yaml-error-${target}`);
    const validationError = validateYamlSyntax(content);
    
    if (validationError) {
        if (errorElement) {
            errorElement.textContent = validationError;
            errorElement.style.display = 'block';
        }
        return;
    }
    
    if (errorElement) {
        errorElement.style.display = 'none';
    }
    
    // Disable the button during save
    const originalText = button.innerHTML;
    button.innerHTML = 'Saving...';
    button.disabled = true;
    
    try {
        const response = await apiPost(`/api/settings/${encodeURIComponent(target)}`, {
            settings_content: content
        });
        
        if (response.ok) {
            toast(`Settings for ${target} saved successfully`, true);
            // Update original content
            if (win) {
                win.originalContent = content;
            }
            // Re-load settings to get fresh content (in case server modified it)
            setTimeout(() => refreshSettings(win), 1000);
        } else {
            toast(`Failed to save settings for ${target}: ${response.error || 'Unknown error'}`, false);
        }
    } catch (e) {
        toast(`Error saving settings for ${target}: ${e.message}`, false);
    } finally {
        button.innerHTML = originalText;
        button.disabled = false;
    }
}

// YAML validation using js-yaml library (loaded from CDN)
function validateYamlSyntax(content) {
    // Try using js-yaml if available
    if (typeof jsyaml !== 'undefined') {
        try {
            jsyaml.load(content);
            return null; // No error
        } catch (e) {
            return `YAML syntax error: ${e.message}`;
        }
    }
    
    // Fallback to simple checks if js-yaml is not loaded
    return simpleYamlValidation(content);
}

function simpleYamlValidation(content) {
    // Basic YAML validation without js-yaml library
    const lines = content.split('\n');
    let indentLevel = -1;
    let inBlock = false;
    
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i].trim();
        if (line === '' || line.startsWith('#')) continue;
        
        // Check for tabs (YAML spec requires spaces)
        if (line.includes('\t')) {
            return 'YAML error: tabs are not allowed, use spaces for indentation';
        }
        
        // Check indentation
        const match = line.match(/^(\s*)/);
        const indent = match ? match[1].length : 0;
        
        if (indentLevel === -1) {
            indentLevel = indent;
        } else if (indent > indentLevel) {
            // Check that indentation increases by exactly 2 (common YAML standard)
            if ((indent - indentLevel) % 2 !== 0) {
                return 'YAML warning: indentation should increase by 2 spaces';
            }
        }
    }
    
    return null; // No errors found with simple validation
}

function setupYamlValidation(target) {
    const win = activeWindows.get(windowKey('settings', target));
    const textarea = $(`settings-textarea-${target}`);
    
    if (!textarea && !win?.codemirrorEditor) return;
    
    // Debounced validation (don't validate on every keystroke)
    let validationTimeout = null;
    
    const validateContent = () => {
        const content = win?.codemirrorEditor ? win.codemirrorEditor.getValue() : textarea.value;
        const errorElement = $(`yaml-error-${target}`);
        const validationError = validateYamlSyntax(content);
        
        if (validationError) {
            if (errorElement) {
                errorElement.textContent = validationError;
                errorElement.style.display = 'block';
            }
        } else {
            if (errorElement) {
                errorElement.style.display = 'none';
            }
        }
    };
    
    // Set up validation for textarea
    if (textarea) {
        textarea.addEventListener('input', () => {
            clearTimeout(validationTimeout);
            validationTimeout = setTimeout(validateContent, 500);
        });
    }
    
    // Set up validation for CodeMirror
    if (win?.codemirrorEditor) {
        win.codemirrorEditor.on('change', () => {
            clearTimeout(validationTimeout);
            validationTimeout = setTimeout(validateContent, 500);
        });
    }
}

// --- NMEA2000 view ----------------------------------------------------
// Single NMEA2000 window per process. The device (PGN stats) view is an
// in-place navigation within the same window; while in device view the
// list auto-refresh is paused and resumes when returning to the list.
function loadJsYaml() {
    if (typeof jsyaml !== 'undefined') return;
    const script = document.createElement('script');
    script.src = 'https://cdn.jsdelivr.net/npm/js-yaml@4.1.0/dist/js-yaml.min.js';
    script.onload = () => {
        console.log('js-yaml loaded');
    };
    script.onerror = () => {
        console.log('js-yaml failed to load, using simple validation');
    };
    document.head.appendChild(script);
}

// Load js-yaml when the page loads
loadJsYaml();

