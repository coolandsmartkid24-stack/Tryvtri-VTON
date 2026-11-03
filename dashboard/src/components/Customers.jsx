import React, { useState, useEffect } from 'react';
import { api } from '../services/api';
import { Search, RefreshCw, User, Mail, ShoppingBag, Clock } from 'lucide-react';

export default function Customers() {
  const [customers, setCustomers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [error, setError] = useState('');

  const loadCustomers = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.getCustomers(50, 0, search);
      setCustomers(res.customers || []);
    } catch (err) {
      setError(err.message || 'Failed to fetch customer list');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadCustomers();
  }, [search]);

  return (
    <div style={{ maxWidth: '1360px', margin: '0 auto', padding: '28px 24px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <div>
          <h2 style={{ fontSize: '22px', fontWeight: '800', letterSpacing: '-0.3px' }}>Customer Management</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '14px', marginTop: '4px' }}>
            Tracking usage, remaining free demo tries, and rolling 24-hour reset windows
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{ position: 'relative' }}>
            <input
              type="text"
              placeholder="Search email or Shopify ID…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{ width: '280px', paddingLeft: '36px' }}
            />
            <Search size={16} color="var(--text-muted)" style={{ position: 'absolute', left: '12px', top: '12px' }} />
          </div>

          <button onClick={loadCustomers} disabled={loading} className="btn-secondary">
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
          marginBottom: '20px'
        }}>
          {error}
        </div>
      )}

      <div className="table-container">
        <table>
          <thead>
            <tr>
              <th>Customer Identity</th>
              <th>Type</th>
              <th>Successful Try-Ons</th>
              <th>Remaining Tries</th>
              <th>Status</th>
              <th>Last Activity</th>
              <th>Next Eligibility</th>
            </tr>
          </thead>
          <tbody>
            {customers.length === 0 ? (
              <tr>
                <td colSpan="7" style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>
                  {loading ? 'Loading customer records…' : 'No customer records found.'}
                </td>
              </tr>
            ) : (
              customers.map((c) => {
                const used = c.success_count || 0;
                const remaining = c.remaining_tries ?? Math.max(0, 2 - used);
                const isExhausted = remaining <= 0;

                return (
                  <tr key={c.id}>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <div style={{
                          width: '32px',
                          height: '32px',
                          borderRadius: '8px',
                          background: 'var(--bg-tertiary)',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          color: 'var(--text-secondary)'
                        }}>
                          {c.email ? <Mail size={16} /> : c.shopify_customer_id ? <ShoppingBag size={16} /> : <User size={16} />}
                        </div>
                        <div>
                          <div style={{ fontWeight: '600' }}>
                            {c.email || c.shopify_customer_id || c.session_id?.slice(0, 16) + '…'}
                          </div>
                          {c.shopify_customer_id && c.email && (
                            <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                              Shopify ID: {c.shopify_customer_id}
                            </div>
                          )}
                        </div>
                      </div>
                    </td>
                    <td>
                      <span className="badge badge-info" style={{ fontSize: '11px' }}>
                        {c.identity_type || 'session'}
                      </span>
                    </td>
                    <td>
                      <span style={{ fontWeight: '700' }}>{used}</span>
                    </td>
                    <td>
                      <span style={{
                        fontWeight: '700',
                        color: remaining > 0 ? 'var(--success)' : 'var(--danger)'
                      }}>
                        {remaining} of 2
                      </span>
                    </td>
                    <td>
                      {isExhausted ? (
                        <span className="badge badge-danger">Quota Exhausted</span>
                      ) : (
                        <span className="badge badge-success">Eligible</span>
                      )}
                    </td>
                    <td style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                      {c.last_activity_at ? new Date(c.last_activity_at).toLocaleString() : '—'}
                    </td>
                    <td style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                      {c.reset_at ? (
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                          <Clock size={12} color="var(--warning)" />
                          {new Date(c.reset_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </span>
                      ) : (
                        'Immediate'
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
