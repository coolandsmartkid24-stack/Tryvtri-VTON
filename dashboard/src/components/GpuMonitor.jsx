import React, { useState, useEffect } from 'react';
import { api } from '../services/api';
import { Cpu, Power, Clock, DollarSign, AlertCircle, ShieldAlert, CheckCircle } from 'lucide-react';

export default function GpuMonitor({ onGpuUpdate }) {
  const [gpu, setGpu] = useState(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState('');
  const [actionMsg, setActionMsg] = useState('');

  const loadStatus = async () => {
    try {
      const res = await api.getGpuStatus();
      setGpu(res);
      if (onGpuUpdate) onGpuUpdate(res);
    } catch (err) {
      setError(err.message || 'Failed to fetch GPU status');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStatus();
    const interval = setInterval(loadStatus, 5000); // 5s fast polling for GPU
    return () => clearInterval(interval);
  }, []);

  const handleStart = async () => {
    if (!confirm('Start Lium GPU pod now? This will begin billable runtime (~$0.36/hour).')) return;
    setActionLoading(true);
    setError('');
    setActionMsg('');
    try {
      const res = await api.startGpu();
      setActionMsg(res.message || 'GPU startup triggered.');
      loadStatus();
    } catch (err) {
      setError(err.message || 'Failed to start GPU');
    } finally {
      setActionLoading(false);
    }
  };

  const handleStop = async () => {
    if (!confirm('Shut down Lium GPU instance now? Any idle resources will be terminated.')) return;
    setActionLoading(true);
    setError('');
    setActionMsg('');
    try {
      const res = await api.stopGpu();
      setActionMsg(res.message || 'GPU shutdown triggered.');
      loadStatus();
    } catch (err) {
      setError(err.message || 'Failed to stop GPU');
    } finally {
      setActionLoading(false);
    }
  };

  const status = gpu?.status || 'stopped';
  const isRunning = status === 'running';

  return (
    <div style={{ maxWidth: '1360px', margin: '0 auto', padding: '28px 24px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <div>
          <h2 style={{ fontSize: '22px', fontWeight: '800', letterSpacing: '-0.3px' }}>GPU Lifecycle Monitor</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '14px', marginTop: '4px' }}>
            On-demand NVIDIA RTX 5080 lifecycle and cost tracking with automatic 10-minute idle termination
          </p>
        </div>

        <div style={{ display: 'flex', gap: '12px' }}>
          {isRunning ? (
            <button
              onClick={handleStop}
              disabled={actionLoading || gpu?.active_requests > 0}
              className="btn-danger"
              style={{ display: 'flex', alignItems: 'center', gap: '8px' }}
            >
              <Power size={16} />
              <span>{actionLoading ? 'Stopping…' : 'Stop GPU Instance'}</span>
            </button>
          ) : (
            <button
              onClick={handleStart}
              disabled={actionLoading || status === 'starting'}
              className="btn-primary"
            >
              <Power size={16} />
              <span>{actionLoading ? 'Starting…' : 'Wake GPU Instance'}</span>
            </button>
          )}
        </div>
      </div>

      {actionMsg && (
        <div style={{ background: 'var(--success-bg)', color: 'var(--success)', padding: '14px 18px', borderRadius: '8px', marginBottom: '20px', border: '1px solid rgba(16,185,129,0.2)' }}>
          {actionMsg}
        </div>
      )}

      {error && (
        <div style={{ background: 'var(--danger-bg)', color: 'var(--danger)', padding: '14px 18px', borderRadius: '8px', marginBottom: '20px', border: '1px solid rgba(239,68,68,0.2)' }}>
          {error}
        </div>
      )}

      {/* Main Status Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '20px', marginBottom: '24px' }}>
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span className="kpi-title">GPU Status</span>
            <Cpu size={20} color="var(--accent-primary)" />
          </div>
          <div style={{ marginTop: '12px', display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span className={`badge ${isRunning ? 'badge-success' : status === 'starting' ? 'badge-warning' : 'badge-danger'}`} style={{ fontSize: '14px', padding: '6px 14px' }}>
              <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'currentColor' }}></span>
              {status}
            </span>
            {gpu?.mock_mode && (
              <span className="badge badge-warning" style={{ fontSize: '11px' }}>Mock / Local</span>
            )}
          </div>
          <div className="kpi-sub" style={{ marginTop: '12px' }}>
            Pod ID: <code style={{ fontFamily: 'var(--font-mono)' }}>{gpu?.pod_id || 'None (Deallocated)'}</code>
          </div>
        </div>

        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span className="kpi-title">Hardware & Pricing</span>
            <DollarSign size={20} color="#10b981" />
          </div>
          <div className="kpi-value" style={{ fontSize: '26px' }}>
            {gpu?.gpu_model || 'NVIDIA RTX 5080'}
          </div>
          <div className="kpi-sub">
            Rate: <strong>${gpu?.price_per_hour?.toFixed(2) || '0.36'}/hour</strong> (~$0.006/min)
          </div>
        </div>

        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span className="kpi-title">Inference Concurrency</span>
            <Clock size={20} color="var(--warning)" />
          </div>
          <div className="kpi-value" style={{ fontSize: '26px' }}>
            {gpu?.active_requests ?? 0} active / {gpu?.queued_requests ?? 0} queued
          </div>
          <div className="kpi-sub">
            {gpu?.active_requests > 0 ? 'GPU actively processing requests' : 'Idle (Auto-stop timer running)'}
          </div>
        </div>

        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span className="kpi-title">Total Estimated Cost</span>
            <DollarSign size={20} color="var(--success)" />
          </div>
          <div className="kpi-value" style={{ color: 'var(--success)' }}>
            ${gpu?.total_estimated_cost_usd?.toFixed(4) || '0.0000'}
          </div>
          <div className="kpi-sub">
            Total runtime: {Math.round((gpu?.total_runtime_seconds || 0) / 60)} minutes
          </div>
        </div>
      </div>

      {/* Safety Policy & Details */}
      <div className="card">
        <h3 style={{ fontSize: '17px', fontWeight: '700', marginBottom: '16px' }}>Autonomous Lifecycle Guardrails</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '20px' }}>
          <div style={{ background: 'var(--bg-secondary)', padding: '18px', borderRadius: '10px' }}>
            <div style={{ fontWeight: '600', marginBottom: '6px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <CheckCircle size={16} color="var(--success)" />
              On-Demand Wakeup
            </div>
            <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
              GPU instance is launched exclusively when a customer initiates virtual try-on. Browsing product pages never starts billable instances.
            </p>
          </div>

          <div style={{ background: 'var(--bg-secondary)', padding: '18px', borderRadius: '10px' }}>
            <div style={{ fontWeight: '600', marginBottom: '6px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Clock size={16} color="var(--warning)" />
              10-Minute Idle Shutdown
            </div>
            <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
              Automatically terminates instance after exactly 600 seconds with zero active or queued requests to prevent accidental overnight charges.
            </p>
          </div>

          <div style={{ background: 'var(--bg-secondary)', padding: '18px', borderRadius: '10px' }}>
            <div style={{ fontWeight: '600', marginBottom: '6px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <ShieldAlert size={16} color="var(--accent-primary)" />
              Concurrency Lock
            </div>
            <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
              Async mutex prevents duplicate instances from launching during simultaneous requests, queuing bursts onto the single leased pod.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
