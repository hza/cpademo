import React, { useEffect, useRef, useState } from "react"
import { useNavigate } from 'react-router-dom'
import axios from "axios"

const API = "http://localhost:8000"

export default function Upload({ onOpenViewer }) {
  const navigate = useNavigate()
  const [uploads, setUploads] = useState([])
  const [dragging, setDragging] = useState(false)
  const [busy, setBusy] = useState(false)
  // no inline expansion; viewer opens in new page
  const inputRef = useRef()

  // Load existing uploads from backend on mount
  useEffect(() => {
    axios.get(`${API}/uploads`).then(res => {
      const existing = res.data.uploads.map(u => ({
        id: u.id,
        name: u.name,
        status: u.has_text ? "Done" : "Uploaded",
        has_text: u.has_text || false,
        uploadedAt: new Date(u.uploadedAt * 1000).toLocaleString(),
        text: null,
      }))
      setUploads(existing)
    }).catch(() => {})
  }, [])

  const doUpload = async (file) => {
    if (!file || busy) return
    setBusy(true)
    const fd = new FormData()
    fd.append("file", file)
    const entry = { id: null, name: file.name, status: "Uploading", uploadedAt: new Date().toLocaleString(), text: null }
    setUploads(prev => [entry, ...prev])
    try {
      const res = await axios.post(`${API}/upload`, fd)
      // refresh server-side listing so the displayed filename matches storage (doc-...)
      try {
        const list = await axios.get(`${API}/uploads`)
        const existing = list.data.uploads.map(u => ({
          id: u.id,
          name: u.name,
          status: u.has_text ? "Done" : "Uploaded",
          has_text: u.has_text || false,
          uploadedAt: new Date(u.uploadedAt * 1000).toLocaleString(),
          text: null,
        }))
        setUploads(existing)
      } catch {
        // fallback to updating the optimistic entry if listing failed
        setUploads(prev => prev.map(u =>
          u.name === file.name && u.status === "Uploading"
            ? { ...u, id: res.data.id, status: "Uploaded" }
            : u
        ))
      }
    } catch {
      setUploads(prev => prev.map(u =>
        u.name === file.name && u.status === "Uploading"
          ? { ...u, status: "Failed" }
          : u
      ))
    } finally {
      setBusy(false)
    }
  }

  const extract = async (id) => {
    setUploads(prev => prev.map(u => u.id === id ? { ...u, status: "Extracting" } : u))
    try {
      const res = await axios.get(`${API}/textract/${id}`)
      setUploads(prev => prev.map(u => u.id === id ? { ...u, status: "Done", text: res.data.text, has_text: true } : u))
    } catch {
      setUploads(prev => prev.map(u => u.id === id ? { ...u, status: "Error" } : u))
    }
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    const f = e.dataTransfer.files[0]
    if (f) doUpload(f)
  }

  const statusBadge = (s) => {
    const cls = { Uploading: "badge-blue", Uploaded: "badge-gray", Extracting: "badge-yellow", Done: "badge-green", Failed: "badge-red", Error: "badge-red" }
    return <span className={`badge ${cls[s] || "badge-gray"}`}>{s}</span>
  }

  return (
    <div>
      {/* Page intro card */}
      <div className="section-header-card">
        <div>
          <h2 className="section-title">My Documents</h2>
          <p className="section-sub">Upload images or PDFs and extract structured text using AWS Textract and then run AI pipelines for further analysis.</p>
        </div>
        <button className="btn-primary" onClick={() => inputRef.current.click()}>
          ⬆ Upload New File
        </button>
        <input ref={inputRef} type="file" accept="image/*,.pdf" style={{ display: "none" }}
          onChange={e => doUpload(e.target.files[0])} />
      </div>

      {/* Drop zone */}
      <div
        className={`dropzone${dragging ? " dragging" : ""}`}
        onDragOver={e => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current.click()}
      >
        <div className="dropzone-icon">📂</div>
        <p className="dropzone-text">Drag &amp; drop a file here, or <span className="dropzone-link">click to browse</span></p>
        <p className="dropzone-hint">PDF, PNG, JPEG, TIFF — up to 10 MB</p>
      </div>

      {/* Uploads table — always visible */}
      <div className="table-card">
          <h3 className="table-title">Recent Uploads</h3>
          <table className="uploads-table">
            <thead>
              <tr>
                <th>FILE</th>
                <th>UPLOADED</th>
                <th>STATUS</th>
                <th>ACTIONS</th>
              </tr>
            </thead>
            <tbody>
              {uploads.map((u, i) => (
                <React.Fragment key={u.id || i}>
                  <tr>
                    <td className="file-name">
                      <a className="file-link" onClick={() => u.id && navigate(`/image/${u.id}`)} style={{ cursor: 'pointer', color: '#0ea5e9' }}>{u.name}</a>
                    </td>
                    <td className="muted">{u.uploadedAt}</td>
                    <td>{statusBadge(u.status)}</td>
                    <td className="actions-cell">
                      {(!u.has_text && u.status === "Uploaded") && (
                        <button className="action-btn" onClick={() => extract(u.id)}>Extract Text</button>
                      )}
                      {(u.has_text || u.status === "Done") && (
                        <button className="action-btn" onClick={async () => {
                          // ensure text exists (extract if needed), then open viewer in-app
                          if (!u.has_text) {
                            await extract(u.id)
                          }
                          if (onOpenViewer) onOpenViewer(u.id)
                        }}>
                          View Text
                        </button>
                      )}
                      <button
                        className="action-btn"
                        style={{ marginLeft: 8 }}
                        onClick={async () => {
                          if (!u.id) return
                          if (!window.confirm(`Delete ${u.name}? This cannot be undone.`)) return
                          try {
                            await axios.delete(`${API}/upload/${u.id}`)
                            // refresh list
                            const list = await axios.get(`${API}/uploads`)
                            const existing = list.data.uploads.map(u => ({
                              id: u.id,
                              name: u.name,
                              status: u.has_text ? "Done" : "Uploaded",
                              has_text: u.has_text || false,
                              uploadedAt: new Date(u.uploadedAt * 1000).toLocaleString(),
                              text: null,
                            }))
                            setUploads(existing)
                          } catch (e) {
                            alert('Failed to delete file')
                          }
                        }}
                        aria-label={`Delete ${u.name}`}
                        title="Delete"
                      >
                        <span role="img" aria-hidden="true" style={{ fontSize: 14 }}>🗑️</span>
                      </button>
                      {(u.status === "Extracting") && <span className="muted">Processing…</span>}
                    </td>
                  </tr>
                  {/* inline preview removed — viewer opens in new page */}
                </React.Fragment>
              ))}
              {uploads.length === 0 && (
                <tr>
                  <td colSpan={4} style={{ textAlign: "center", padding: "32px", color: "#94a3b8" }}>
                    No uploads yet. Drop a file above to get started.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
    </div>
  )
}
