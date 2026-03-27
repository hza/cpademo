import React from "react"

export default function ModelPicker({ model, onChange, disabled, options = [], datalistId = 'models' }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
      <label htmlFor={datalistId + '-input'} style={{ opacity: disabled ? 0.4 : 1 }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: '#334155', whiteSpace: 'nowrap' }}>LLM Model: </span>
      </label>
      <input
        id={datalistId + '-input'}
        list={datalistId}
        value={model}
        onChange={e => onChange(e.target.value)}
        placeholder="Type or select a model…"
        disabled={disabled}
        style={{
          height: 36,
          padding: '6px 10px', borderRadius: 6, border: '1px solid #cbd5e1',
          fontFamily: 'ui-monospace, "Fira Code", monospace', fontSize: 13, minWidth: 260,
          boxSizing: 'border-box',
          opacity: disabled ? 0.4 : 1,
        }}
      />
      <datalist id={datalistId}>
        {options.map((o, i) => <option key={i} value={o} />)}
      </datalist>

      <button
        onClick={() => {
          try {
            const url = 'https://openrouter.ai/' + (model || '')
            window.open(url, '_blank')
          } catch (e) {
            // ignore
          }
        }}
        aria-label="View on OpenRouter"
        title="Open model page on OpenRouter"
        style={{
          width: 36,
          height: 36,
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: 0,
          borderRadius: 6,
          border: '1px solid #cbd5e1',
          background: '#eef2ff',
          color: '#3730a3',
          cursor: 'pointer',
          marginLeft: 4,
        }}
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M18 13v6a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
          <polyline points="15 3 21 3 21 9" />
          <line x1="10" y1="14" x2="21" y2="3" />
        </svg>
      </button>
    </div>
  )
}
