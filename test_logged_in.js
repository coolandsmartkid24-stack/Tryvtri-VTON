const fs = require('fs');

async function testLoggedIn() {
  const tabs = await fetch('http://127.0.0.1:9222/json').then(r => r.json());
  const pageTab = tabs.find(t => t.type === 'page');
  const ws = new WebSocket(pageTab.webSocketDebuggerUrl);
  let msgId = 1;

  // 1. Get real token from API
  const loginRes = await fetch('https://tryvtri-vton.vercel.app/admin/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'admin', password: 'tryvtri_admin_2026!' })
  }).then(r => r.json());
  
  const token = loginRes.access_token;
  console.log('Login succeeded! Token:', token.slice(0, 15) + '...');

  ws.onopen = () => {
    ws.send(JSON.stringify({ id: msgId++, method: 'Page.enable' }));
    ws.send(JSON.stringify({ id: msgId++, method: 'Runtime.enable' }));
    // Navigate and set token in localStorage
    ws.send(JSON.stringify({ 
      id: msgId++, 
      method: 'Page.navigate', 
      params: { url: 'https://tryvtri-vton.vercel.app/dashboard/' } 
    }));
    setTimeout(() => {
      ws.send(JSON.stringify({
        id: msgId++,
        method: 'Runtime.evaluate',
        params: {
          expression: `localStorage.setItem('tryvtri_admin_token', '${token}'); localStorage.setItem('tryvtri_admin_user', 'admin'); location.reload();`
        }
      }));
    }, 1500);

    setTimeout(() => {
      ws.send(JSON.stringify({ id: 888, method: 'Page.captureScreenshot', params: { format: 'png' } }));
    }, 4500);
  };

  ws.onmessage = (msg) => {
    const data = JSON.parse(msg.data);
    if (data.id) console.log('Response for ID:', data.id, 'Has error:', !!data.error, 'Has result:', !!data.result);
    if (data.id === 888 && data.result) {
      fs.writeFileSync('E:/VTON_GARMENTS/dashboard_overview_live.png', Buffer.from(data.result.data, 'base64'));
      console.log('Successfully saved screenshot to E:/VTON_GARMENTS/dashboard_overview_live.png !');
    }
  };

  setTimeout(() => process.exit(0), 6500);
}
testLoggedIn();
