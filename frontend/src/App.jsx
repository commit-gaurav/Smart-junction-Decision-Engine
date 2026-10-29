import React, { useState, useEffect } from 'react'

export default function App() {
  const [backendHealth, setBackendHealth] = useState({
    status: 'checking...',
    mode: 'simulation_only',
  })

  useEffect(() => {
    fetch('http://127.0.0.1:8000/api/health')
      .then((res) => res.json())
      .then((data) => setBackendHealth(data))
      .catch(() =>
        setBackendHealth({
          status: 'backend offline (start FastAPI on :8000)',
          mode: 'simulation_only',
        })
      )
  }, [])

  return (
    <div style={{ fontFamily: 'system-ui, -apple-system, sans-serif', margin: '2rem', maxWidth: '800px', lineHeight: '1.5' }}>
      <header style={{ borderBottom: '2px solid #e2e8f0', paddingBottom: '1rem', marginBottom: '1.5rem' }}>
        <h1 style={{ margin: 0, fontSize: '1.75rem', color: '#1e293b' }}>
          Smart Junction Decision Engine
        </h1>
        <p style={{ margin: '0.5rem 0 0', color: '#64748b' }}>
          Four-way intersection adaptive traffic controller simulation (NESW)
        </p>
        <div style={{ marginTop: '0.75rem', display: 'inline-block', background: '#fef2f2', border: '1px solid #f87171', color: '#991b1b', padding: '0.25rem 0.75rem', borderRadius: '4px', fontSize: '0.85rem', fontWeight: 600 }}>
          Simulation Mode: Does not transmit instructions to hardware
        </div>
      </header>

      <section style={{ background: '#f8fafc', padding: '1.25rem', borderRadius: '8px', border: '1px solid #e2e8f0', marginBottom: '1.5rem' }}>
        <h2 style={{ fontSize: '1.1rem', marginTop: 0, color: '#334155' }}>Backend Status</h2>
        <p style={{ margin: '0.25rem 0' }}>
          <strong>API Health:</strong> <code style={{ background: '#e2e8f0', padding: '0.1rem 0.4rem', borderRadius: '4px' }}>{backendHealth.status}</code>
        </p>
        <p style={{ margin: '0.25rem 0' }}>
          <strong>Execution Mode:</strong> <code style={{ background: '#e2e8f0', padding: '0.1rem 0.4rem', borderRadius: '4px' }}>{backendHealth.mode}</code>
        </p>
      </section>

      <section style={{ border: '1px solid #e2e8f0', borderRadius: '8px', padding: '1.25rem' }}>
        <h2 style={{ fontSize: '1.1rem', marginTop: 0, color: '#334155' }}>Software-Demo Configuration Defaults</h2>
        <ul style={{ margin: 0, paddingLeft: '1.25rem', color: '#475569' }}>
          <li>Approaches: <strong>North (N), East (E), South (S), West (W)</strong> (mutually exclusive)</li>
          <li>Green duration bounds: <strong>8s min</strong> to <strong>45s max</strong></li>
          <li>Yellow clearance: <strong>3s</strong></li>
          <li>All-Red clearance: <strong>1s</strong></li>
          <li>Fairness maximum wait ceiling: <strong>90s</strong></li>
          <li>Planning engine tick: <strong>1s</strong></li>
        </ul>
        <small style={{ display: 'block', marginTop: '0.75rem', color: '#94a3b8' }}>
          * Editable demo simulation defaults, not certified road-engineering guidance.
        </small>
      </section>
    </div>
  )
}

