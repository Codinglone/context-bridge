// Background service worker
// Handles messages from popup to content scripts

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'getServerUrl') {
        sendResponse({ url: 'http://localhost:8080' });
    }
    return true;
});

// Open options page on install
chrome.runtime.onInstalled.addListener(() => {
    console.log('Context Bridge extension installed');
});
