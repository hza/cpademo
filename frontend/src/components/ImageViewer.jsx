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
      <div className="section-header-card" style={{ alignItems: 'center' }}>
        <div>
          <h2 className="section-title">View Original</h2>
          <p className="section-sub">Viewing original file for <span style={{ fontFamily: 'ui-monospace, "Fira Code", monospace', fontWeight: 700 }}>{displayName || docId}</span></p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn-primary" style={{ background: '#94a3b8' }} onClick={onBack}>Back</button>
          <button className="btn-primary" style={{ background: '#0ea5e9' }} onClick={async () => {
            if (!docId) return
            setOcrLoading(true)
            setOcrText(null)
            try {
              const res = await axios.post(`${API}/vllm/ocr/${docId}`)
              setOcrText(res.data.text)
            } catch (e) {
              setOcrText(`OCR failed: ${e?.response?.data?.detail || e.message || e}`)
            } finally {
              setOcrLoading(false)
            }
          }}>{ocrLoading ? 'Running OCR…' : 'OCR with LLM'}</button>
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
          <pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'inherit' }}>{ocrText}</pre>
        </div>
      )}
    </div>
  )
}
