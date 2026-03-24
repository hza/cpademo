import React from "react"

export default function Profile() {
  return (
    <div>
      {/* Header */}
      <div className="section-header-card">
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <div style={{ width: 56, height: 56, borderRadius: '50%', background: '#2563eb', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: 18, flexShrink: 0 }}>JA</div>
          <div>
            <h2 className="section-title" style={{ marginBottom: 2 }}>John Anderson</h2>
            <p className="section-sub">CPA — Anderson CPA LLC</p>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn-primary">Edit Profile</button>
        </div>
      </div>

      {/* Details */}
      <div className="table-card" style={{ padding: '0 0 8px' }}>
        <div className="table-title">Account Details</div>
        {[
          { label: 'Full Name',     value: 'John Anderson' },
          { label: 'Role',          value: 'CPA' },
          { label: 'Organisation',  value: 'Anderson CPA LLC' },
          { label: 'Email',         value: 'john.anderson@example.com' },
          { label: 'Location',      value: 'New York, NY' },
        ].map(({ label, value }) => (
          <div key={label} style={{ display: 'flex', alignItems: 'center', padding: '13px 20px', borderBottom: '1px solid #f1f5f9' }}>
            <span style={{ width: 160, fontSize: 12, fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.6px', flexShrink: 0 }}>{label}</span>
            <span style={{ fontSize: 14, color: '#0f172a' }}>{value}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
