import React, { useEffect, useState } from "react"
import axios from "axios"
import { useParams } from "react-router-dom"

const API = "http://localhost:8000"

export default function ImageViewer({ id, onBack }) {
  const params = useParams()
  const docId = id || params.id
  const [url, setUrl] = useState(null)
  const [type, setType] = useState(null)
  const [displayName, setDisplayName] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [ocrLoading, setOcrLoading] = useState(false)
  const [ocrText, setOcrText] = useState(null)
  const [model, setModel] = useState('google/gemini-2.0-flash-001')
  const [ocrMethod, setOcrMethod] = useState('vllm')

  useEffect(() => {
    if (!docId) return
    setLoading(true)
    const fetchBlob = async () => {
      try {
        const res = await axios.get(`${API}/download/${docId}`, { responseType: 'blob' })
        const ct = (res.headers['content-type'] || '').toLowerCase()
        const blobUrl = URL.createObjectURL(res.data)
        setUrl(blobUrl)
        setType(ct)
      } catch (err) {
        setError(err?.message || 'Failed to load file')
      } finally {
        setLoading(false)
      }
    }
    fetchBlob()
    // fetch filename from uploads metadata if available
    const fetchMeta = async () => {
      try {
        const res = await axios.get(`${API}/uploads`)
        const item = (res.data.uploads || []).find(u => String(u.id) === String(docId))
        if (item && item.name) setDisplayName(item.name)
      } catch (e) {
        // ignore metadata errors
      }
    }
    fetchMeta()
    return () => {
      if (url) URL.revokeObjectURL(url)
    }
  }, [docId])

  return (
    <div>
      <div className="section-header-card" style={{ alignItems: 'flex-start' }}>
        <div>
          <h2 className="section-title">Document</h2>
          <p className="section-sub">Original file: <span style={{ fontFamily: 'ui-monospace, "Fira Code", monospace', fontWeight: 700 }}>{displayName || docId}</span></p>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, alignItems: 'flex-end' }}>
          {/* Row 1: radio buttons */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <span style={{ fontSize: 13, color: '#64748b', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>OCR via</span>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontWeight: ocrMethod === 'vllm' ? 600 : 400 }}>
              <input type="radio" name="ocrMethod" value="vllm" checked={ocrMethod === 'vllm'} onChange={() => setOcrMethod('vllm')} />
              LLM
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontWeight: ocrMethod === 'textract' ? 600 : 400 }}>
              <input type="radio" name="ocrMethod" value="textract" checked={ocrMethod === 'textract'} onChange={() => setOcrMethod('textract')} />
              Textract
            </label>
          </div>

          {/* Row 2: model picker + OCR button + Back */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            Model:
            <input
              list="vllm-models"
              value={model}
              onChange={e => setModel(e.target.value)}
              placeholder="Type or select a model…"
              disabled={ocrMethod === 'textract'}
              style={{
                padding: '6px 10px', borderRadius: 6, border: '1px solid #cbd5e1',
                fontFamily: 'ui-monospace, "Fira Code", monospace', fontSize: 13, minWidth: 260,
                opacity: ocrMethod === 'textract' ? 0.4 : 1,
              }}
            />
            <datalist id="vllm-models">
              <option value="google/gemini-2.0-flash-001" />
              <option value="google/gemini-2.5-flash" />
              <option value="google/gemini-3-flash-preview" />
              <option value="anthropic/claude-3" />
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
              style={{
                padding: '7px 12px',
                fontSize: 13,
                borderRadius: 6,
                border: '1px solid #cbd5e1',
                background: '#eef2ff',
                color: '#3730a3',
                cursor: 'pointer',
                marginLeft: 8,
              }}
              title="Open model page on OpenRouter"
            >
              View on OpenRouter
            </button>
            <button className="btn-primary" style={{ background: '#0ea5e9' }} disabled={ocrLoading} onClick={async () => {
              if (!docId) return
              setOcrLoading(true)
              setOcrText(null)
              try {
                if (ocrMethod === 'textract') {
                  const res = await axios.get(`${API}/textract/${docId}`)
                  setOcrText(res.data.text)
                } else {
                  const res = await axios.post(`${API}/vllm/ocr/${docId}?model=${encodeURIComponent(model)}`)
                  setOcrText(res.data.text)
                }
              } catch (e) {
                setOcrText(`OCR failed: ${e?.response?.data?.detail || e.message || e}`)
              } finally {
                setOcrLoading(false)
              }
            }}>{ocrLoading ? 'Running OCR…' : (ocrMethod === 'textract' ? 'OCR with Textract' : 'OCR with LLM')}</button>
  
            <button className="btn-primary" style={{ background: '#94a3b8', marginLeft: 8 }} onClick={onBack}>Back</button>
          </div>
        </div>
      </div>

      <div className="table-card" style={{ padding: 20, minHeight: '60vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        {loading && <div style={{ color: '#64748b' }}>Loading…</div>}
        {error && <div style={{ color: '#dc2626' }}>{error}</div>}
        {!loading && !error && url && (
          type.startsWith('image/') ? (
            <img src={url} alt={docId} style={{ maxWidth: '100%', maxHeight: '80vh', borderRadius: 8 }} />
          ) : type === 'application/pdf' ? (
            <iframe src={url} title={docId} style={{ width: '100%', height: '80vh', border: 'none' }} />
          ) : (
            <a href={url} download style={{ color: '#0ea5e9' }}>Download file</a>
          )
        )}
      </div>
      {ocrLoading && <div style={{ padding: 12, color: '#64748b' }}>Running OCR with visual LLM…</div>}
      {ocrText && (
        <div className="table-card" style={{ marginTop: 12 }}>
          <h3 className="table-title">OCR Result</h3>
          <pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'monospace' }}>{ocrText}</pre>
        </div>
      )}
    </div>
  )
}
