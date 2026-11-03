import React, { useState, useEffect } from 'react';
import { api } from '../services/api';
import { 
  Users, CheckCircle2, XCircle, Zap, AlertTriangle, 
  Clock, Cpu, DollarSign, RefreshCw 
} from 'lucide-react';

export default function Overview({ onNavigate }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [windowHours, setWindowHours] = useState(24);
  const [error, setError] = useState('');

  const loadData = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.getDashboard(windowHours);
      setData(res);
    } catch (err) {
      setError(err.message || 'Failed to load dashboard metrics');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 15000); // 15s auto refresh
    return () => clearInterval(interval);
  }, [windowHours]);

  const metrics = data?.metrics || {};
  const gpu = data?.gpu || {};

  return (
    <div style={{ maxWidth: '1360px', margin: '0 auto', padding: '28px 24px' }}>
      {/* Header and Controls */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <div>
          <h2 style={{ fontSize: '22px', fontWeight: '800', letterSpacing: '-0.3px' }}>System Overview</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '14px', marginTop: '4px' }}>
            Live metrics connected to Supabase and Lium RTX 5080
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <select
            value={windowHours}
            onChange={(e) => setWindowHours(Number(e.target.value))}
            style={{ fontSize: '13px', padding: '8px 12px' }}
          >
            <option value={24}>Rolling 24 Hours</option>
            <option value={48}>Rolling 48 Hours</option>
            <option value={168}>Last 7 Days</option>
          </select>

          <button
            onClick={loadData}
            disabled={loading}
            className="btn-secondary"
            style={{ padding: '8px 14px' }}
          >
            <RefreshCw size={14} className={loading ? 'spin' : ''} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {error && (
        <div style={{
          background: 'var(--danger-bg)',
          color: 'var(--danger)',
          padding: '14px 18px',
          borderRadius: '8px',
          marginBottom: '20px',
          border: '1px solid rgba(239,68,68,0.2)'
        }}>
          {error}
        </div>
      )}

      {/* KPI Cards Grid */}
      <div className="grid-kpi">
        <div className="kpi-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span className="kpi-title">Total Registered Customers</span>
            <Users size={20} color="var(--accent-primary)" />
          </div>
          <div className="kpi-value">{metrics.total_registered_customers ?? 0}</div>
          <div className="kpi-sub">Unique Shopify & storefront visitors</div>
        </div>

        <div className="kpi-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span className="kpi-title">Customers Used Demo</span>
            <Zap size={20} color="#8b5cf6" />
          </div>
          <div className="kpi-value">{metrics.customers_used_demo ?? 0}</div>
          <div className="kpi-sub">Attempted at least 1 virtual try-on</div>
        </div>

        <div className="kpi-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span className="kpi-title">Successful Try-Ons</span>
            <CheckCircle2 size={20} color="var(--success)" />
          </div>
          <div className="kpi-value" style={{ color: 'var(--success)' }}>
            {metrics.total_successful_tryons ?? 0}
          </div>
          <div className="kpi-sub">FASHN VTON 1.5 photorealistic results</div>
        </div>

        <div className="kpi-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span className="kpi-title">Failed Try-Ons</span>
            <XCircle size={20} color="var(--danger)" />
          </div>
          <div className="kpi-value" style={{ color: 'var(--danger)' }}>
            {metrics.total_failed_tryons ?? 0}
          </div>
          <div className="kpi-sub">Never consumes customer quota</div>
        </div>

        <div className="kpi-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span className="kpi-title">Free Tries Consumed</span>
            <Clock size={20} color="var(--warning)" />
          </div>
          <div className="kpi-value">{metrics.total_free_tries_consumed ?? 0}</div>
          <div className="kpi-sub">Strict 2 tries / 24h rolling policy</div>
        </div>

        <div className="kpi-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span className="kpi-title">Quota Exhausted</span>
            <AlertTriangle size={20} color="var(--warning)" />
          </div>
          <div className="kpi-value" style={{ color: 'var(--warning)' }}>
            {metrics.customers_quota_exhausted ?? 0}
          </div>
          <div className="kpi-sub">Used all 2 tries within 24h window</div>
        </div>

        <div className="kpi-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span className="kpi-title">Currently Eligible</span>
            <CheckCircle2 size={20} color="var(--success)" />
          </div>
          <div className="kpi-value" style={{ color: 'var(--success)' }}>
            {metrics.customers_currently_eligible ?? 0}
          </div>
          <div className="kpi-sub">Eligible for another virtual try-on</div>
        </div>

        <div className="kpi-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span className="kpi-title">Est. GPU Spending</span>
            <DollarSign size={20} color="#10b981" />
          </div>
          <div className="kpi-value">${gpu.total_estimated_cost_usd?.toFixed(4) ?? '0.0000'}</div>
          <div className="kpi-sub">Lium RTX 5080 at ~$0.36/hour</div>
        </div>
      </div>

      {/* GPU Quick Overview Card */}
      <div className="card" style={{ marginTop: '24px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px' }}>
          <div>
            <h3 style={{ fontSize: '16px', fontWeight: '700' }}>On-Demand GPU Lifecycle Status</h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>
              NVIDIA RTX 5080 automatically shuts down after 10 minutes of inactivity
            </p>
          </div>
          <button onClick={() => onNavigate('gpu')} className="btn-secondary" style={{ fontSize: '13px' }}>
            <Cpu size={14} />
            <span>Open GPU Controller</span>
          </button>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px' }}>
          <div style={{ background: 'var(--bg-secondary)', padding: '16px', borderRadius: '8px' }}>
            <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>CURRENT STATE</div>
            <div style={{ fontSize: '18px', fontWeight: '700', marginTop: '4px', textTransform: 'capitalize' }}>
              {gpu.status || 'Stopped'}
            </div>
          </div>
          <div style={{ background: 'var(--bg-secondary)', padding: '16px', borderRadius: '8px' }}>
            <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>GPU HARDWARE</div>
            <div style={{ fontSize: '18px', fontWeight: '700', marginTop: '4px' }}>
              {gpu.gpu_model || 'RTX 5080 (16 GB)'}
            </div>
          </div>
          <div style={{ background: 'var(--bg-secondary)', padding: '16px', borderRadius: '8px' }}>
            <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>ACTIVE REQUESTS</div>
            <div style={{ fontSize: '18px', fontWeight: '700', marginTop: '4px' }}>
              {gpu.active_requests ?? 0} active / {gpu.queued_requests ?? 0} queued
            </div>
          </div>
          <div style={{ background: 'var(--bg-secondary)', padding: '16px', borderRadius: '8px' }}>
            <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>TOTAL RUNTIME</div>
            <div style={{ fontSize: '18px', fontWeight: '700', marginTop: '4px' }}>
              {Math.round((gpu.total_runtime_seconds || 0) / 60)} minutes
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
