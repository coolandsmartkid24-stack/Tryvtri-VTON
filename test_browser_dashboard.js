const http = require('http');

async function test() {
  const tabs = await fetch('http://127.0.0.1:9222/json').then(r => r.json());
  const pageTab = tabs.find(t => t.type === 'page');
  if (!pageTab) {
    console.error('Page tab not found:', tabs);
    return;
  }
  const ws = new WebSocket(pageTab.webSocketDebuggerUrl);
  let msgId = 1;

  ws.onopen = () => {
    ws.send(JSON.stringify({ id: msgId++, method: 'Page.enable' }));
    ws.send(JSON.stringify({ id: msgId++, method: 'Runtime.enable' }));
    ws.send(JSON.stringify({ id: msgId++, method: 'Log.enable' }));
    ws.send(JSON.stringify({ id: msgId++, method: 'Network.enable' }));
    // Reload page to catch all network requests and console errors from beginning
    ws.send(JSON.stringify({ id: msgId++, method: 'Page.navigate', params: { url: 'https://tryvtri-vton.vercel.app/dashboard/' } }));
  };

  ws.onmessage = (msg) => {
    const data = JSON.parse(msg.data);
    if (data.method === 'Runtime.consoleAPICalled') {
      console.log('[BROWSER CONSOLE]', data.params.type, JSON.stringify(data.params.args));
    }
    if (data.method === 'Runtime.exceptionThrown') {
      console.error('[BROWSER EXCEPTION]', JSON.stringify(data.params.exceptionDetails));
    }
    if (data.method === 'Network.responseReceived') {
      console.log('[NETWORK RESPONSE]', data.params.response.url, data.params.response.status, data.params.response.mimeType);
    }
    if (data.method === 'Network.loadingFailed') {
      console.error('[NETWORK FAILED]', data.params.requestId, data.params.errorText);
    }
  };

  setTimeout(async () => {
    ws.send(JSON.stringify({ id: 999, method: 'Page.captureScreenshot', params: { format: 'png' } }));
  }, 3500);

  ws.onmessage = (msg) => {
    const data = JSON.parse(msg.data);
    if (data.id === 999 && data.result) {
      const fs = require('fs');
      fs.writeFileSync('E:/VTON_GARMENTS/dashboard_live.png', Buffer.from(data.result.data, 'base64'));
      console.log('Successfully saved screenshot to E:/VTON_GARMENTS/dashboard_live.png !');
    }
  };

  setTimeout(() => process.exit(0), 5000);
}
test();
