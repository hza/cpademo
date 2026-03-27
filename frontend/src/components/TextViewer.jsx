import React, { useEffect, useState } from "react"
import axios from "axios"
import { useParams } from "react-router-dom"

const API = "http://localhost:8000"

export default function TextViewer({ id, onBack, onDetectGL }) {
  const params = useParams()
  const docId = id || params.id
  const [text, setText] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!docId) return
    setLoading(true)
    axios.get(`${API}/textract/${docId}`).then(res => {
      setText(res.data.text || "")
    }).catch(err => {
      setError(err?.message || "Failed to fetch text")
    }).finally(() => setLoading(false))
  }, [docId])

  const download = () => {
    const blob = new Blob([text || ""], { type: "text/plain" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${docId}.txt`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  }

  const downloadOriginal = async () => {
    if (!docId) return
    setLoading(true)
    try {
      const res = await axios.get(`${API}/download/${docId}`, { responseType: 'blob' })
      const cd = res.headers['content-disposition'] || ''
      let filename = `${docId}`
      const m = cd.match(/filename="?([^";]+)"?/) || cd.match(/filename=([^;]+)/)
      if (m && m[1]) filename = m[1].trim()
      const url = URL.createObjectURL(res.data)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (err) {
      setError(err?.message || 'Download failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <div className="section-header-card" style={{ alignItems: 'center' }}>
        <div>
          <h2 className="section-title">Extracted Text</h2>
          <p className="section-sub">Viewing text for <span style={{ fontFamily: 'ui-monospace, "Fira Code", monospace', fontWeight: 700 }}>{docId}</span></p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            className="btn-primary"
            onClick={() => onDetectGL && onDetectGL(docId, text)}
            disabled={!text || !String(text).trim()}
            title={!text || !String(text).trim() ? 'No OCR text available' : 'Open AI Detector'}
          >
            Open AI Detector
          </button>
          <button className="btn-primary" onClick={download}>Download Text</button>
          <button className="btn-primary" onClick={downloadOriginal} style={{ background: '#6ee7b7', color: '#063' }}>Download Image</button>
          <button className="btn-primary" style={{ background: '#94a3b8' }} onClick={onBack}>Back</button>
        </div>
      </div>

      <div className="table-card" style={{ padding: 20, maxHeight: '60vh', overflow: 'hidden' }}>
        {loading && <div style={{ color: '#64748b' }}>Loading…</div>}
        {error && <div style={{ color: '#dc2626' }}>{error}</div>}
        {!loading && !error && (
          <pre style={{ maxHeight: '55vh', whiteSpace: 'pre-wrap', fontFamily: 'ui-monospace, "Fira Code", monospace', fontSize: 13, color: '#0f172a', overflowY: 'auto', padding: 12, borderRadius: 8, background: '#fbfdff' }}>{text}</pre>
        )}
      </div>
    </div>
  )
}
