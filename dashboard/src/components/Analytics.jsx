import React, { useState, useEffect } from 'react';
import { api } from '../services/api';
import { BarChart3, TrendingUp, CheckCircle, XCircle, Clock, ShoppingCart } from 'lucide-react';

export default function Analytics() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(30);
  const [error, setError] = useState('');

  const loadAnalytics = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.getUsage(days);
      setData(res);
    } catch (err) {
      setError(err.message || 'Failed to fetch analytics data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAnalytics();
  }, [days]);

  const daily = data?.daily_usage || [];
  const products = data?.product_usage || [];
  const recent = data?.recent_activity || [];

  return (
    <div style={{ maxWidth: '1360px', margin: '0 auto', padding: '28px 24px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <div>
          <h2 style={{ fontSize: '22px', fontWeight: '800', letterSpacing: '-0.3px' }}>Usage Analytics</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '14px', marginTop: '4px' }}>
            Daily virtual try-on trends, product breakdown, and real-time generation activity
          </p>
        </div>

        <select
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          style={{ fontSize: '13px', padding: '8px 12px' }}
        >
          <option value={7}>Last 7 Days</option>
          <option value={14}>Last 14 Days</option>
          <option value={30}>Last 30 Days</option>
          <option value={90}>Last 90 Days</option>
        </select>
      </div>

      {error && (
        <div style={{ background: 'var(--danger-bg)', color: 'var(--danger)', padding: '14px 18px', borderRadius: '8px', marginBottom: '20px' }}>
          {error}
        </div>
      )}

      {/* Daily Usage Table */}
      <div className="card" style={{ marginBottom: '24px' }}>
        <h3 style={{ fontSize: '16px', fontWeight: '700', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <TrendingUp size={18} color="var(--accent-primary)" />
          Daily Generations (Success vs Failed)
        </h3>

        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Total Requests</th>
                <th>Successful</th>
                <th>Failed</th>
                <th>Success Rate</th>
              </tr>
            </thead>
            <tbody>
              {daily.length === 0 ? (
                <tr>
                  <td colSpan="5" style={{ textAlign: 'center', padding: '30px', color: 'var(--text-muted)' }}>
                    No daily generation activity recorded yet.
                  </td>
                </tr>
              ) : (
                daily.map((d, i) => {
                  const total = (d.successful || 0) + (d.failed || 0);
                  const rate = total > 0 ? Math.round((d.successful / total) * 100) : 0;
                  return (
                    <tr key={i}>
                      <td style={{ fontWeight: '600' }}>{d.date || d.day}</td>
                      <td>{total}</td>
                      <td style={{ color: 'var(--success)' }}>{d.successful || 0}</td>
                      <td style={{ color: 'var(--danger)' }}>{d.failed || 0}</td>
                      <td>
                        <span className="badge badge-info">{rate}%</span>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(450px, 1fr))', gap: '24px' }}>
        {/* Product Breakdown */}
        <div className="card">
          <h3 style={{ fontSize: '16px', fontWeight: '700', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <ShoppingCart size={18} color="var(--accent-primary)" />
            Product Breakdown
          </h3>

          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Product Title</th>
                  <th>Category</th>
                  <th>Total Try-Ons</th>
                </tr>
              </thead>
              <tbody>
                {products.length === 0 ? (
                  <tr>
                    <td colSpan="3" style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)' }}>
                      No product usage data recorded yet.
                    </td>
                  </tr>
                ) : (
                  products.map((p, i) => (
                    <tr key={i}>
                      <td style={{ fontWeight: '600' }}>{p.product_title || p.product_id || 'Storefront Product'}</td>
                      <td>
                        <span className="badge badge-info" style={{ fontSize: '11px' }}>
                          {p.garment_category || 'tops'}
                        </span>
                      </td>
                      <td style={{ fontWeight: '700' }}>{p.total_tryons || p.count || 0}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Recent Activity Feed */}
        <div className="card">
          <h3 style={{ fontSize: '16px', fontWeight: '700', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Clock size={18} color="var(--accent-primary)" />
            Recent Activity Log
          </h3>

          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Product</th>
                  <th>Status</th>
                  <th>Latency</th>
                </tr>
              </thead>
              <tbody>
                {recent.length === 0 ? (
                  <tr>
                    <td colSpan="4" style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)' }}>
                      No recent activity recorded.
                    </td>
                  </tr>
                ) : (
                  recent.map((a, i) => (
                    <tr key={i}>
                      <td style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                        {a.created_at ? new Date(a.created_at).toLocaleTimeString() : '—'}
                      </td>
                      <td style={{ fontWeight: '500', fontSize: '13px' }}>
                        {a.product_title || a.product_id || 'Garment'}
                      </td>
                      <td>
                        {a.status === 'success' ? (
                          <span className="badge badge-success" style={{ fontSize: '10px' }}>Success</span>
                        ) : a.status === 'failed' ? (
                          <span className="badge badge-danger" style={{ fontSize: '10px' }}>Failed</span>
                        ) : (
                          <span className="badge badge-warning" style={{ fontSize: '10px' }}>Pending</span>
                        )}
                      </td>
                      <td style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                        {a.duration_ms ? `${(a.duration_ms / 1000).toFixed(1)}s` : '—'}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
