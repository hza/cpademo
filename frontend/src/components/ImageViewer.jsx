import React, { useEffect, useState } from "react"
import axios from "axios"
import { useParams } from "react-router-dom"
import ModelPicker from "./ModelPicker"

const API = "http://localhost:8000"

export default function ImageViewer({ id, onBack, onDetectGL }) {
  const params = useParams()
  const docId = id || params.id
  const [url, setUrl] = useState(null)
  const [type, setType] = useState(null)
  const [displayName, setDisplayName] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [ocrLoading, setOcrLoading] = useState(false)
  const [ocrText, setOcrText] = useState(null)
  const [ocrRequested, setOcrRequested] = useState(false)
  const [hasText, setHasText] = useState(false)
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
        if (item) {
          setHasText(!!item.has_text)
          if (item.has_text) {
            try {
              const r = await axios.get(`${API}/textract/${docId}`)
              setOcrText(r.data.text)
              setOcrRequested(true)
            } catch (e) {
              // ignore text fetch errors
            }
          }
        }
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

          {/* Row 2: model picker (own line) + OCR button + Back */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'flex-end' }}>
            <div style={{ width: '100%', display: 'flex', justifyContent: 'flex-end' }}>
              <ModelPicker
                model={model}
                onChange={setModel}
                disabled={ocrMethod === 'textract'}
                datalistId="vllm-models"
                options={[
                  'google/gemini-2.0-flash-001',
                  'google/gemini-2.5-flash',
                  'google/gemini-3-flash-preview',
                  'mistralai/pixtral-large-2411',
                ]}
              />
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <button className="btn-primary" style={{ background: '#0ea5e9' }} disabled={ocrLoading} onClick={async () => {
                if (!docId) return
                setOcrRequested(true)
                setOcrLoading(true)
                setOcrText(null)
                try {
                  if (ocrMethod === 'textract') {
                    const res = await axios.get(`${API}/textract/${docId}?fresh=1`)
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

              <button
                className="btn-primary"
                onClick={() => onDetectGL && onDetectGL(docId, ocrText || '')}
                disabled={!((ocrText && String(ocrText).trim()) || hasText)}
                title={!((ocrText && String(ocrText).trim()) || hasText) ? 'Run OCR first to enable detector' : 'Open AI Detector'}
              >
                Open AI Detector
              </button>

              <button className="btn-primary" style={{ background: '#94a3b8', marginLeft: 8 }} onClick={onBack}>Back</button>
            </div>
          </div>
        </div>
      </div>

      <div className="table-card" style={{ padding: 10, minHeight: '60vh', display: 'flex', gap: 12, alignItems: 'stretch' }}>
        {/* Left: image/pdf display */}
        <div style={{ width: '40%', minWidth: 320, display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ marginBottom: 8 }}>
            <h3 className="table-title" style={{ margin: 0 }}>Image</h3>
          </div>
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'flex-start', paddingTop: 8, minHeight: '60vh' }}>
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
        </div>

        {/* Right: OCR text */}
        <div style={{ width: '60%', minWidth: 320, maxWidth: '60%', display: 'flex', flexDirection: 'column' }}>
          <div style={{ marginBottom: 8, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <h3 className="table-title" style={{ margin: 0 }}>OCR Result</h3>
          </div>
          {ocrLoading && <div style={{ padding: 12, color: '#64748b' }}>Running OCR with visual LLM…</div>}
          <div style={{ flex: 1, overflowY: 'auto', padding: 12, borderRadius: 8, background: '#fbfdff' }}>
            {ocrText ? (
              <pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'ui-monospace, "Fira Code", monospace', fontSize: 11, margin: 0 }}>{ocrText}</pre>
            ) : (!ocrRequested ? (
              <div style={{ color: '#64748b' }}>No OCR result yet. Run OCR from the controls above.</div>
            ) : null)}
          </div>
        </div>
      </div>
    </div>
  )
}
