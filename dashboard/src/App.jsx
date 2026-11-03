import React, { useState, useEffect } from 'react';
import { auth, api } from './services/api';
import Navbar from './components/Navbar';
import Overview from './components/Overview';
import Customers from './components/Customers';
import Analytics from './components/Analytics';
import GpuMonitor from './components/GpuMonitor';
import Login from './components/Login';

export default function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(auth.isAuthenticated());
  const [activeTab, setActiveTab] = useState('overview');
  const [gpuStatus, setGpuStatus] = useState(null);

  useEffect(() => {
    if (isAuthenticated) {
      api.getGpuStatus().then(setGpuStatus).catch(() => {});
    }
  }, [isAuthenticated]);

  const handleLogout = () => {
    auth.clearSession();
    setIsAuthenticated(false);
  };

  if (!isAuthenticated) {
    return <Login onLoginSuccess={() => setIsAuthenticated(true)} />;
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        onLogout={handleLogout}
        gpuStatus={gpuStatus}
      />

      <main style={{ flex: 1, paddingBottom: '40px' }}>
        {activeTab === 'overview' && <Overview onNavigate={setActiveTab} />}
        {activeTab === 'customers' && <Customers />}
        {activeTab === 'analytics' && <Analytics />}
        {activeTab === 'gpu' && <GpuMonitor onGpuUpdate={setGpuStatus} />}
      </main>

      <footer style={{
        textAlign: 'center',
        padding: '20px',
        borderTop: '1px solid var(--border)',
        fontSize: '12px',
        color: 'var(--text-muted)'
      }}>
        TryVtri Virtual Try-On • Powered by FASHN VTON 1.5 & Lium Cloud GPU • Zero-Credential Architecture
      </footer>
    </div>
  );
}
