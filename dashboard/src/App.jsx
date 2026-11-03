import React, { useState, useEffect } from 'react';
import { auth, api, setOnUnauthorized } from './services/api';
import Navbar from './components/Navbar';
import Overview from './components/Overview';
import Customers from './components/Customers';
import Analytics from './components/Analytics';
import GpuMonitor from './components/GpuMonitor';
import Login from './components/Login';

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }
  componentDidCatch(error, errorInfo) {
    console.error("Dashboard caught error:", error, errorInfo);
  }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: '#0a0c10',
          color: '#f3f4f6',
          padding: '24px',
          fontFamily: 'sans-serif'
        }}>
          <div className="card" style={{ maxWidth: '480px', width: '100%', padding: '32px', textAlign: 'center' }}>
            <h2 style={{ fontSize: '20px', marginBottom: '12px', color: '#ef4444' }}>Dashboard Encountered an Error</h2>
            <p style={{ fontSize: '13px', color: '#9ca3af', marginBottom: '20px', lineHeight: 1.5 }}>
              {this.state.error?.message || 'An unexpected rendering error occurred.'}
            </p>
            <button
              onClick={() => {
                localStorage.clear();
                window.location.reload();
              }}
              className="btn-primary"
              style={{ padding: '10px 20px', borderRadius: '8px', cursor: 'pointer' }}
            >
              Reset Session & Re-Login
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

function DashboardApp() {
  const [isAuthenticated, setIsAuthenticated] = useState(auth.isAuthenticated());
  const [activeTab, setActiveTab] = useState('overview');
  const [gpuStatus, setGpuStatus] = useState(null);

  useEffect(() => {
    setOnUnauthorized(() => {
      setIsAuthenticated(false);
    });
  }, []);

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

export default function App() {
  return (
    <ErrorBoundary>
      <DashboardApp />
    </ErrorBoundary>
  );
}
