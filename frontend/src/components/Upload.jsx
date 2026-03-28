import React, { useEffect, useRef, useState } from "react"
import { useNavigate } from 'react-router-dom'
import axios from "axios"
import { API } from "../config"

export default function Upload({ onOpenViewer }) {
  const navigate = useNavigate()
  const [uploads, setUploads] = useState([])
  const [dragging, setDragging] = useState(false)
  const [busy, setBusy] = useState(false)
  const [documentLink, setDocumentLink] = useState("")
  const [linkError, setLinkError] = useState("")
  const [highlightedId, setHighlightedId] = useState(null)
  const [highlightedName, setHighlightedName] = useState(null)
  const highlightTimer = useRef(null)
  const filenameFromUrl = (url) => {
    try {
      const u = new URL(url)
      const name = decodeURIComponent(u.pathname.split('/').pop() || '')
      return name || url
    } catch (e) {
      return url
    }
  }
  // no inline expansion; viewer opens in new page
  const inputRef = useRef()

  // Load existing uploads from backend on mount
  useEffect(() => {
    refreshUploads()
  }, [])

  const refreshUploads = async () => {
    try {
      const res = await axios.get(`${API}/uploads`)
      const existing = res.data.uploads.map(u => ({
        id: u.id,
        name: u.name,
        status: u.has_text ? "Done" : "Uploaded",
        has_text: u.has_text || false,
        uploadedAt: new Date(u.uploadedAt * 1000).toLocaleString(),
        text: null,
      }))
      setUploads(existing)
    } catch {
    }
  }

  const clearHighlight = () => {
    if (highlightTimer.current) {
      clearTimeout(highlightTimer.current)
      highlightTimer.current = null
    }
    setHighlightedId(null)
    setHighlightedName(null)
  }

  const setTemporaryHighlight = (id, name) => {
    clearHighlight()
    if (id) setHighlightedId(id)
    else if (name) setHighlightedName(name)
    // clear after 4s
    highlightTimer.current = setTimeout(() => {
      setHighlightedId(null)
      setHighlightedName(null)
      highlightTimer.current = null
    }, 15000)
  }

  const genPasteName = (mime) => {
    const id = Math.random().toString(36).slice(2,16)
    let ext = 'png'
    try {
      if (mime && mime.includes('/')) ext = mime.split('/')[1].split(';')[0]
    } catch (e) {}
    return `Paste-${id}.${ext}`
  }

  const handlePaste = (e) => {
    if (busy) return
    try {
      const items = e.clipboardData && e.clipboardData.items
      if (!items) return
      for (let i = 0; i < items.length; i++) {
        const it = items[i]
        if (it.kind === 'file') {
          const f = it.getAsFile()
          if (f && f.type && f.type.startsWith('image/')) {
            const name = genPasteName(f.type)
            const newFile = new File([f], name, { type: f.type })
            doUpload(newFile)
            e.preventDefault()
            return
          }
        }
        // fallback: if plain text contains an image URL, attempt link upload
        if (it.kind === 'string' && it.type === 'text/plain') {
          it.getAsString((s) => {
            const txt = (s || '').trim()
            if (/^https?:\/\/.+\.(png|jpe?g|gif|webp|svg)(\?.*)?$/i.test(txt)) {
              setDocumentLink(txt)
              uploadDocumentLink()
            }
          })
        }
      }
    } catch (e) {
      // ignore paste errors
    }
  }

  // Attach global paste handler so Cmd+V works anywhere on the page
  React.useEffect(() => {
    const globalHandler = (ev) => {
      try {
        // ignore pastes into form inputs or contenteditable areas
        const tg = ev.target
        if (!tg) return
        const tagName = tg.tagName && tg.tagName.toLowerCase()
        const isEditable = tagName === 'input' || tagName === 'textarea' || tg.isContentEditable
        if (isEditable) return
        handlePaste(ev)
      } catch (err) {
        // swallow
      }
    }

    window.addEventListener('paste', globalHandler)
    return () => window.removeEventListener('paste', globalHandler)
  }, [busy])

  const doUpload = async (file) => {
    if (!file || busy) return
    setLinkError("")
    setBusy(true)
    const fd = new FormData()
    fd.append("file", file)
    const entry = { id: null, name: file.name, status: "Uploading", uploadedAt: new Date().toLocaleString(), text: null }
    setUploads(prev => [entry, ...prev])
    setTemporaryHighlight(null, file.name)
    try {
      const res = await axios.post(`${API}/upload`, fd)
      // refresh server-side listing so the displayed filename matches storage (doc-...)
      try {
        await refreshUploads()
        try {
          const newId = res?.data?.id
          if (newId) setTemporaryHighlight(newId, null)
        } catch (e) {}
      } catch {
        // fallback to updating the optimistic entry if listing failed
        setUploads(prev => prev.map(u =>
          u.name === file.name && u.status === "Uploading"
            ? { ...u, status: "Uploaded" }
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

  const uploadDocumentLink = async () => {
    const url = documentLink.trim()
    if (!url || busy) return

    setLinkError("")
    setBusy(true)
    const displayName = filenameFromUrl(url)
    const entry = { id: null, name: displayName, status: "Uploading", uploadedAt: new Date().toLocaleString(), text: null }
    setUploads(prev => [entry, ...prev])
    setTemporaryHighlight(null, displayName)

    try {
      const res = await axios.post(`${API}/upload-link`, { url })
      setDocumentLink("")
      await refreshUploads()
      try {
        const newId = res?.data?.id
        if (newId) setTemporaryHighlight(newId, null)
      } catch (e) {}
    } catch (error) {
      const message = error?.response?.data?.detail || "Failed to download document link"
      setLinkError(message)
      setUploads(prev => prev.map(u =>
        u.name === url && u.status === "Uploading"
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

  return (
    <div>
      {/* Page intro card */}
      <div className="section-header-card">
        <div className="section-header-main">
          <h2 className="section-title">My Documents</h2>
          <p className="section-sub">Upload images or PDFs and extract structured text using <a target="_blank" href='https://us-east-1.console.aws.amazon.com/costmanagement/home?region=us-east-1#/freetier'>AWS Textract</a> and then run AI pipelines for further analysis.</p>
        </div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <button className="btn-primary" onClick={() => inputRef.current.click()} disabled={busy}>
            ⬆ Upload New File
          </button>
        </div>
        <input ref={inputRef} type="file" accept="image/*,.pdf" style={{ display: "none" }}
          onChange={e => doUpload(e.target.files[0])} />
      </div>

      {/* Drop zone */}
      <div
        className={`dropzone${dragging ? " dragging" : ""}`}
        onDragOver={e => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => !busy && inputRef.current.click()}
      >
        <div className="dropzone-icon">📂</div>
        <p className="dropzone-text">Drag an image here or <span className="dropzone-link">upload a file</span></p>
        <p className="dropzone-hint">PDF, PNG, JPEG, TIFF — up to 10 MB</p>

        <div className="or-divider" aria-hidden="true"><span>OR</span></div>

        <div className="link-upload-row" onClick={e => e.stopPropagation()}>
          <label className="sr-only" htmlFor="document-link">Paste image or image link</label>
          <input
            id="document-link"
            className="link-upload-input"
            type="url"
            placeholder="Paste image or image link"
            value={documentLink}
            onChange={e => setDocumentLink(e.target.value)}
            onKeyDown={e => {
              if (e.key === "Enter") {
                e.preventDefault()
                uploadDocumentLink()
              }
            }}
            disabled={busy}
          />
          <button className="link-upload-btn" onClick={uploadDocumentLink} disabled={busy || !documentLink.trim()}>
            Upload
          </button>
        </div>
        {linkError && <p className="link-upload-error">{linkError}</p>}
      </div>

      {/* Uploads table — always visible */}
      <div className="table-card">
          <h3 className="table-title">Recent Uploads</h3>
          <table className="uploads-table">
            <thead>
              <tr>
                <th>FILE</th>
                <th>UPLOADED</th>
                <th>ACTIONS</th>
              </tr>
            </thead>
            <tbody>
              {uploads.map((u, i) => (
                <React.Fragment key={u.id || i}>
                <tr className={(u.id && u.id === highlightedId) || (!u.id && highlightedName && u.name === highlightedName) ? 'row-highlight' : ''}>
                    <td className="file-name">
                      <a className="file-link" onClick={() => u.id && navigate(`/image/${u.id}`)} style={{ cursor: 'pointer', color: '#0ea5e9', textDecoration: 'underline' }}>{u.name}</a>
                    </td>
                    <td className="muted">{u.uploadedAt}</td>
                    <td className="actions-cell">
                      {u.status === "Uploading" ? (
                        <div className="upload-dots" aria-hidden="true">
                          <span></span><span></span><span></span>
                        </div>
                      ) : (
                        <>
                          <button
                            className="action-btn"
                            title="View"
                            aria-label="View"
                            style={{ padding: '6px 10px', fontSize: 16, lineHeight: 1 }}
                            onClick={async () => {
                              // ensure text exists (extract if needed), then open viewer in-app
                              if (!u.has_text) {
                                await extract(u.id)
                              }
                              if (onOpenViewer) onOpenViewer(u.id)
                            }}
                          >
                            <span role="img" aria-hidden="true">✏️</span>
                          </button>
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
                        </>
                      )}
                    </td>
                  </tr>
                  {/* inline preview removed — viewer opens in new page */}
                </React.Fragment>
              ))}
              {uploads.length === 0 && (
                <tr>
                  <td colSpan={3} style={{ textAlign: "center", padding: "32px", color: "#94a3b8" }}>
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
