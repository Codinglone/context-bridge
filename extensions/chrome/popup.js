// Popup script - fetches and displays available tools
const CB_SERVER = 'http://localhost:8080';

async function init() {
    const statusEl = document.getElementById('status');
    const toolsSection = document.getElementById('tools-section');

    try {
        const healthResp = await fetch(`${CB_SERVER}/mcp/v1/health`);
        const health = await healthResp.json();
        statusEl.textContent = 'Connected — ' + Object.keys(health.connectors).length + ' connectors active';
        statusEl.style.color = '#90EE90';
    } catch (err) {
        statusEl.textContent = 'Not connected — start Context Bridge server';
        statusEl.style.color = '#FFB6C1';
        toolsSection.innerHTML = `
            <div class="error">
                <p>Cannot connect to Context Bridge</p>
                <p style="margin-top: 8px; font-size: 12px;">Run: context-bridge serve --transport http</p>
            </div>
        `;
        return;
    }

    try {
        const toolsResp = await fetch(`${CB_SERVER}/mcp/v1/tools`);
        const data = await toolsResp.json();
        const tools = data.tools || [];

        if (tools.length === 0) {
            toolsSection.innerHTML = '<div class="section">No tools configured. Add connectors to config.yaml.</div>';
            return;
        }

        // Group by connector
        const groups = {};
        tools.forEach(tool => {
            const prefix = tool.name.split('.')[0];
            if (!groups[prefix]) groups[prefix] = [];
            groups[prefix].push(tool);
        });

        let html = '';
        Object.keys(groups).sort().forEach(prefix => {
            html += `<div class="section">`;
            html += `<div class="section-title">${prefix}</div>`;
            groups[prefix].forEach(tool => {
                html += `
                    <div class="tool-row">
                        <div>
                            <div class="tool-name">${tool.name}</div>
                            <div class="tool-desc">${tool.description || ''}</div>
                        </div>
                        <button class="tool-btn" data-tool="${tool.name}">Use</button>
                    </div>
                `;
            });
            html += `</div>`;
        });

        toolsSection.innerHTML = html;

        // Add click handlers
        toolsSection.querySelectorAll('.tool-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const toolName = btn.dataset.tool;
                chrome.tabs.query({active: true, currentWindow: true}, tabs => {
                    chrome.tabs.sendMessage(tabs[0].id, {
                        action: 'openTool',
                        toolName: toolName,
                    });
                    window.close();
                });
            });
        });

    } catch (err) {
        toolsSection.innerHTML = `<div class="error">Error loading tools: ${err.message}</div>`;
    }
}

document.addEventListener('DOMContentLoaded', init);
