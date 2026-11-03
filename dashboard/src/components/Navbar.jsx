import React from 'react';
import { LayoutDashboard, Users, BarChart3, Cpu, LogOut, Sparkles } from 'lucide-react';
import { auth } from '../services/api';

export default function Navbar({ activeTab, setActiveTab, onLogout, gpuStatus }) {
  const user = auth.getUser() || 'admin';

  const navItems = [
    { id: 'overview', label: 'Overview', icon: LayoutDashboard },
    { id: 'customers', label: 'Customers', icon: Users },
    { id: 'analytics', label: 'Analytics', icon: BarChart3 },
    { id: 'gpu', label: 'GPU Monitor', icon: Cpu },
  ];

  const getGpuBadge = () => {
    if (!gpuStatus) return null;
    const status = gpuStatus.status || 'stopped';
    let badgeClass = 'badge-danger';
    if (status === 'running') badgeClass = 'badge-success';
    else if (status === 'starting' || status === 'stopping') badgeClass = 'badge-warning';

    return (
      <span className={`badge ${badgeClass}`} style={{ fontSize: '11px', padding: '3px 8px' }}>
        <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'currentColor' }}></span>
        GPU: {status}
      </span>
    );
  };

  return (
    <header style={{
      background: 'var(--bg-secondary)',
      borderBottom: '1px solid var(--border)',
      position: 'sticky',
      top: 0,
      zIndex: 50,
      padding: '0 24px'
    }}>
      <div style={{
        maxWidth: '1360px',
        margin: '0 auto',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        height: '68px'
      }}>
        {/* Brand */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{
            width: '38px',
            height: '38px',
            borderRadius: '10px',
            background: 'linear-gradient(135deg, #3b82f6, #1d4ed8)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 4px 12px rgba(59, 130, 246, 0.3)'
          }}>
            <Sparkles size={20} color="#fff" />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontWeight: '800', fontSize: '17px', letterSpacing: '-0.3px' }}>TryVtri</span>
              <span style={{ fontSize: '11px', fontWeight: '700', background: 'var(--bg-tertiary)', padding: '2px 6px', borderRadius: '4px', color: 'var(--accent-primary)', border: '1px solid var(--border)' }}>
                FASHN 1.5
              </span>
            </div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Zero-Credential VTON Admin</div>
          </div>
        </div>

        {/* Navigation Tabs */}
        <nav style={{ display: 'flex', gap: '6px' }}>
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '8px 16px',
                  borderRadius: '8px',
                  fontSize: '14px',
                  fontWeight: '600',
                  color: isActive ? '#fff' : 'var(--text-secondary)',
                  background: isActive ? 'var(--bg-tertiary)' : 'transparent',
                  border: isActive ? '1px solid var(--border)' : '1px solid transparent',
                  cursor: 'pointer'
                }}
              >
                <Icon size={17} color={isActive ? 'var(--accent-primary)' : 'currentColor'} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        {/* Right Info & Actions */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          {getGpuBadge()}

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', borderLeft: '1px solid var(--border)', paddingLeft: '16px' }}>
            <div style={{ fontSize: '13px', textAlign: 'right' }}>
              <div style={{ fontWeight: '600', color: 'var(--text-primary)' }}>{user}</div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Administrator</div>
            </div>
            <button
              onClick={onLogout}
              title="Sign Out"
              className="btn-secondary"
              style={{ padding: '8px 12px', fontSize: '13px' }}
            >
              <LogOut size={15} />
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}
