import React, { useEffect, useState } from "react"
import { useParams, useNavigate } from "react-router-dom"
import { API } from "../config"

export default function GLResult({ result, onBack, loading = false, model = '' }) {
  const params = useParams()
  const docId = params.id
  const navigate = useNavigate()
  const [content, setContent] = useState(result || '')
  const [detModel, setDetModel] = useState(model || '')

  useEffect(() => {
    // if we don't have a result (e.g. after page refresh), try to load persisted LLM result
    let cancelled = false
    const fetchSaved = async () => {
      if (content && content.length > 0) return
      try {
        const res = await fetch(`${API}/llm/${docId}`)
        if (res.ok) {
          const j = await res.json()
          if (!cancelled) {
            setContent(j.text || '')
            if (!detModel && j.model) setDetModel(j.model || '')
          }
        }
      } catch (e) {
        // ignore
      }
    }
    fetchSaved()
    return () => { cancelled = true }
  }, [docId])

  return (
    <div>
      <div className="section-header-card" style={{ alignItems: 'center' }}>
        <div>
          <h2 className="section-title">GL Detection Result</h2>
          <p className="section-sub">Result returned by the {detModel ? <span style={{ fontFamily: 'ui-monospace, "Fira Code", monospace', fontWeight: 700 }}>{detModel}</span> : ''} model</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn-primary" onClick={() => navigate('/')}>Close</button>
          <button className="btn-primary" style={{ background: '#94a3b8', marginLeft: 8 }} onClick={() => (navigate(`/gl/${docId}`))}>Back</button>
        </div>
      </div>

      <div className="table-card" style={{ padding: 20 }}>
        <h3 style={{ margin: '8px 0' }}>AI Answer</h3>
        {loading && (!result || result.length === 0) ? (
          <div style={{ textAlign: 'center', padding: 24 }}>
            <style>{`
              @keyframes dance { 0% { transform: translateY(0) } 50% { transform: translateY(-8px) } 100% { transform: translateY(0) } }
              .dance { display:inline-block; margin:0 6px; font-size:28px; animation: dance 0.8s ease-in-out infinite; }
              .dance:nth-child(2){ animation-delay:0.12s } .dance:nth-child(3){ animation-delay:0.24s }
            `}</style>
            <div style={{ fontSize: 12 }}>Waiting for LLM response…</div>
            <div style={{ marginTop: 12 }}>
              <span className="dance">.</span>
              <span className="dance">.</span>
              <span className="dance">.</span>
            </div>
          </div>
        ) : (
          <>
            <pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'ui-monospace, "Fira Code", monospace', fontSize: 13, color: '#0f172a', padding: 12, borderRadius: 8, background: '#fbfdff', maxHeight: '240px', overflowY: 'auto' }}>{content}</pre>
            {(!loading && content && content.length > 0) && (
              <div style={{ marginTop: 8, color: '#64748b', fontSize: 12 }}>AI may make mistakes — verify before using.</div>
            )}
          </>
        )}
      </div>

      <div className="table-card" style={{ padding: 20, marginTop: 12 }}>
        <h3 style={{ margin: '8px 0' }}>Important</h3>
        <div style={{ color: '#334155', fontSize: 14 }}>Next step is to get data based on GL Code (Extractor)</div>
      </div>
    </div>
  )
}
