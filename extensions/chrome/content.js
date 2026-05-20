"""Content script that injects Context Bridge UI into chat interfaces."""

// Detect which chat platform we're on
const PLATFORM = (() => {
    const host = window.location.host;
    if (host.includes('chat.openai.com') || host.includes('chatgpt.com')) return 'chatgpt';
    if (host.includes('claude.ai')) return 'claude';
    if (host.includes('poe.com')) return 'poe';
    return 'unknown';
})();

const CB_SERVER = 'http://localhost:8080';

// Create Context Bridge trigger button
function createTriggerButton() {
    const btn = document.createElement('button');
    btn.id = 'cb-trigger';
    btn.textContent = '@context';
    btn.title = 'Insert context from Context Bridge';
    btn.style.cssText = `
        position: fixed;
        bottom: 80px;
        right: 20px;
        z-index: 2147483647;
        background: #0066cc;
        color: white;
        border: none;
        border-radius: 20px;
        padding: 10px 20px;
        font-size: 14px;
        font-weight: 600;
        cursor: pointer;
        box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        font-family: -apple-system, BlinkMacSystemFont, sans-serif;
    `;
    btn.addEventListener('click', openContextPicker);
    document.body.appendChild(btn);
}

// Open context picker modal
function openContextPicker() {
    // Remove existing modal
    const existing = document.getElementById('cb-modal');
    if (existing) existing.remove();

    const modal = document.createElement('div');
    modal.id = 'cb-modal';
    modal.style.cssText = `
        position: fixed;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        width: 600px;
        max-width: 90vw;
        max-height: 80vh;
        background: white;
        border-radius: 12px;
        box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        z-index: 2147483647;
        display: flex;
        flex-direction: column;
        font-family: -apple-system, BlinkMacSystemFont, sans-serif;
    `;

    modal.innerHTML = `
        <div id="cb-header" style="padding: 16px 20px; border-bottom: 1px solid #e0e0e0; display: flex; justify-content: space-between; align-items: center;">
            <h2 style="margin: 0; font-size: 18px; color: #333;">Context Bridge</h2>
            <button id="cb-close" style="background: none; border: none; font-size: 20px; cursor: pointer; color: #666;">&times;</button>
        </div>
        <div id="cb-loading" style="padding: 40px; text-align: center; color: #666;">
            Loading tools...
        </div>
        <div id="cb-content" style="display: none; overflow-y: auto; padding: 16px;"></div>
    `;

    document.body.appendChild(modal);

    document.getElementById('cb-close').addEventListener('click', () => modal.remove());

    // Close on backdrop click
    modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.remove();
    });

    // Load tools
    loadTools();
}

// Fetch and display tools
async function loadTools() {
    try {
        const resp = await fetch(`${CB_SERVER}/mcp/v1/tools`);
        const data = await resp.json();
        const tools = data.tools || [];

        document.getElementById('cb-loading').style.display = 'none';
        const content = document.getElementById('cb-content');
        content.style.display = 'block';

        // Group tools by connector prefix
        const groups = {};
        tools.forEach(tool => {
            const prefix = tool.name.split('.')[0];
            if (!groups[prefix]) groups[prefix] = [];
            groups[prefix].push(tool);
        });

        let html = '<div style="display: flex; gap: 8px; margin-bottom: 16px;">';
        html += '<input type="text" id="cb-search" placeholder="Search tools..." style="flex: 1; padding: 8px 12px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px;">';
        html += '</div>';

        Object.keys(groups).sort().forEach(prefix => {
            html += `<div class="cb-group" style="margin-bottom: 16px;">`;
            html += `<div style="font-weight: 600; color: #666; font-size: 12px; text-transform: uppercase; margin-bottom: 8px;">${prefix}</div>`;
            groups[prefix].forEach(tool => {
                html += `
                    <div class="cb-tool" data-name="${tool.name}" style="padding: 12px; border: 1px solid #e0e0e0; border-radius: 8px; margin-bottom: 8px; cursor: pointer; transition: background 0.2s;">
                        <div style="font-weight: 600; color: #0066cc; font-size: 14px;">${tool.name}</div>
                        <div style="color: #666; font-size: 13px; margin-top: 4px;">${tool.description || ''}</div>
                    </div>
                `;
            });
            html += `</div>`;
        });

        content.innerHTML = html;

        // Add click handlers
        content.querySelectorAll('.cb-tool').forEach(el => {
            el.addEventListener('click', () => {
                const toolName = el.dataset.name;
                openToolForm(toolName);
            });
            el.addEventListener('mouseenter', () => {
                el.style.background = '#f5f5f5';
            });
            el.addEventListener('mouseleave', () => {
                el.style.background = 'transparent';
            });
        });

        // Search filter
        document.getElementById('cb-search').addEventListener('input', (e) => {
            const term = e.target.value.toLowerCase();
            content.querySelectorAll('.cb-tool').forEach(el => {
                const text = el.textContent.toLowerCase();
                el.style.display = text.includes(term) ? 'block' : 'none';
            });
        });

    } catch (err) {
        document.getElementById('cb-loading').innerHTML = `
            <div style="color: #d32f2f;">Error: ${err.message}</div>
            <div style="margin-top: 8px; font-size: 13px;">Make sure Context Bridge is running on ${CB_SERVER}</div>
        `;
    }
}

// Open form for a specific tool
function openToolForm(toolName) {
    const modal = document.getElementById('cb-modal');
    modal.innerHTML = `
        <div id="cb-header" style="padding: 16px 20px; border-bottom: 1px solid #e0e0e0; display: flex; justify-content: space-between; align-items: center;">
            <h2 style="margin: 0; font-size: 18px; color: #333;">${toolName}</h2>
            <button id="cb-back" style="background: none; border: none; font-size: 14px; cursor: pointer; color: #0066cc;">&larr; Back</button>
        </div>
        <div id="cb-form" style="padding: 20px;"></div>
        <div id="cb-result" style="padding: 0 20px 20px; display: none;"></div>
    `;

    document.getElementById('cb-back').addEventListener('click', openContextPicker);

    // Build form from parameters
    const form = document.getElementById('cb-form');
    form.innerHTML = `
        <div style="color: #666; margin-bottom: 16px; font-size: 14px;">
            Enter arguments and click Execute to fetch context.
        </div>
        <div id="cb-fields"></div>
        <button id="cb-execute" style="margin-top: 16px; width: 100%; padding: 12px; background: #0066cc; color: white; border: none; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer;">
            Execute
        </button>
    `;

    const fields = document.getElementById('cb-fields');

    // For now, create generic JSON input
    // In a full implementation, we'd parse the JSON schema from tool.parameters
    fields.innerHTML = `
        <label style="display: block; margin-bottom: 8px; font-weight: 600; font-size: 14px;">Arguments (JSON)</label>
        <textarea id="cb-args" style="width: 100%; min-height: 120px; padding: 12px; border: 1px solid #ddd; border-radius: 8px; font-family: monospace; font-size: 13px; resize: vertical;" placeholder='{"path": "README.md"}'></textarea>
    `;

    document.getElementById('cb-execute').addEventListener('click', async () => {
        const argsText = document.getElementById('cb-args').value;
        let args = {};
        try {
            args = JSON.parse(argsText || '{}');
        } catch (e) {
            alert('Invalid JSON: ' + e.message);
            return;
        }

        document.getElementById('cb-execute').textContent = 'Loading...';
        document.getElementById('cb-execute').disabled = true;

        try {
            const resp = await fetch(`${CB_SERVER}/mcp/v1/tools/${toolName}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(args),
            });
            const data = await resp.json();

            const resultDiv = document.getElementById('cb-result');
            resultDiv.style.display = 'block';

            if (data.error) {
                resultDiv.innerHTML = `<div style="color: #d32f2f; padding: 12px; background: #ffebee; border-radius: 8px;">${data.error}</div>`;
            } else {
                const resultText = typeof data.result === 'string' ? data.result : JSON.stringify(data.result, null, 2);
                resultDiv.innerHTML = `
                    <div style="margin-bottom: 12px; display: flex; gap: 8px;">
                        <button id="cb-insert" style="flex: 1; padding: 10px; background: #4caf50; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 600;">Insert into Chat</button>
                        <button id="cb-copy" style="flex: 1; padding: 10px; background: #f5f5f5; border: 1px solid #ddd; border-radius: 6px; cursor: pointer;">Copy to Clipboard</button>
                    </div>
                    <pre style="background: #f5f5f5; padding: 16px; border-radius: 8px; overflow-x: auto; font-size: 13px; max-height: 300px; overflow-y: auto;"><code>${escapeHtml(resultText)}</code></pre>
                `;

                document.getElementById('cb-copy').addEventListener('click', () => {
                    navigator.clipboard.writeText(resultText);
                    document.getElementById('cb-copy').textContent = 'Copied!';
                    setTimeout(() => {
                        document.getElementById('cb-copy').textContent = 'Copy to Clipboard';
                    }, 2000);
                });

                document.getElementById('cb-insert').addEventListener('click', () => {
                    insertIntoChat(resultText);
                    modal.remove();
                });
            }
        } catch (err) {
            document.getElementById('cb-result').innerHTML = `<div style="color: #d32f2f;">Error: ${err.message}</div>`;
        } finally {
            document.getElementById('cb-execute').textContent = 'Execute';
            document.getElementById('cb-execute').disabled = false;
        }
    });
}

// Insert text into the chat input
function insertIntoChat(text) {
    let input;

    if (PLATFORM === 'chatgpt') {
        input = document.querySelector('textarea[placeholder*="Message"], #prompt-textarea');
    } else if (PLATFORM === 'claude') {
        input = document.querySelector('[contenteditable="true"]');
    } else if (PLATFORM === 'poe') {
        input = document.querySelector('textarea');
    }

    if (!input) {
        // Fallback: copy to clipboard and notify
        navigator.clipboard.writeText(text);
        showNotification('Context copied to clipboard. Paste into the chat input.');
        return;
    }

    if (input.tagName === 'TEXTAREA') {
        const start = input.selectionStart || 0;
        const end = input.selectionEnd || 0;
        const before = input.value.substring(0, start);
        const after = input.value.substring(end);
        input.value = before + text + after;
        input.dispatchEvent(new Event('input', { bubbles: true }));
    } else if (input.isContentEditable) {
        input.textContent += '\n\n' + text + '\n\n';
        input.dispatchEvent(new Event('input', { bubbles: true }));
    }

    showNotification('Context inserted into chat!');
}

function showNotification(message) {
    const notif = document.createElement('div');
    notif.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: #4caf50;
        color: white;
        padding: 12px 20px;
        border-radius: 8px;
        z-index: 2147483647;
        font-family: sans-serif;
        font-size: 14px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
    `;
    notif.textContent = message;
    document.body.appendChild(notif);
    setTimeout(() => notif.remove(), 3000);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Initialize
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', createTriggerButton);
} else {
    createTriggerButton();
}
