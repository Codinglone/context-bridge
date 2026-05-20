# Context Bridge - Chrome Extension

Browser extension that injects Context Bridge tools into web-based chatbots (ChatGPT, Claude, Poe).

## Installation

### From Source (Developer Mode)

1. Open Chrome and go to `chrome://extensions/`
2. Enable **Developer mode** (toggle in top right)
3. Click **Load unpacked**
4. Select this directory (`extensions/chrome/`)
5. The Context Bridge icon should appear in your toolbar

### Prerequisites

- Context Bridge server must be running locally:
  ```bash
  context-bridge serve --transport http
  ```
- Default server URL: `http://localhost:8080`

## Usage

### Method 1: Floating Trigger Button (On Chat Pages)

When you visit ChatGPT, Claude, or Poe, a **@context** button appears in the bottom-right corner of the page.

1. Click **@context**
2. Browse available tools (filesystem, GitHub, Obsidian, etc.)
3. Select a tool and enter arguments
4. Click **Execute**
5. Click **Insert into Chat** or **Copy to Clipboard**

### Method 2: Extension Popup (From Toolbar)

1. Click the Context Bridge icon in your browser toolbar
2. See all available connectors and tools
3. Click **Use** on any tool
4. The content script will open the tool picker on the current page

## Supported Platforms

| Platform | URL Pattern | Status |
|----------|-------------|--------|
| ChatGPT | chat.openai.com, chatgpt.com | ✅ Supported |
| Claude | claude.ai | ✅ Supported |
| Poe | poe.com | ✅ Supported |

## Architecture

```
Browser Extension
├── content.js          # Injected into chat pages (UI + tool picker)
├── popup.html/js       # Extension popup (tool browser)
├── background.js       # Service worker (message routing)
└── manifest.json       # Extension config

↕ HTTP requests to localhost:8080

Context Bridge Server
├── HTTP transport
├── Connectors (fs, github, obsidian, pg, docker, ssh)
└── Router / Dispatcher
```

## Customization

### Change Server URL

Edit `content.js` and `popup.js`:
```javascript
const CB_SERVER = 'http://localhost:8080';  // Change this
```

### Add More Platforms

Edit `manifest.json` content_scripts matches:
```json
"content_scripts": [{
    "matches": [
        "https://chat.openai.com/*",
        "https://your-new-platform.com/*"
    ],
    ...
}]
```

## Troubleshooting

**"Cannot connect to Context Bridge"**
- Make sure `context-bridge serve --transport http` is running
- Check that `http://localhost:8080/mcp/v1/health` loads in your browser
- Verify CORS is enabled in Context Bridge config

**Tools don't appear**
- Check Context Bridge config has connectors configured
- Verify the server has permissions (firewall, etc.)

**"Insert into Chat" doesn't work**
- The chat platform may have changed their DOM structure
- Fallback: use "Copy to Clipboard" and paste manually

## Security Note

This extension communicates only with `localhost:8080`. It does not send your data to any remote server. The Context Bridge server runs locally on your machine.

## License

MIT
