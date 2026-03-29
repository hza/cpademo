import React, { useState, useEffect } from "react"
import axios from "axios"
import { useParams } from "react-router-dom"
import { API } from "../config"
import ModelPicker from "./ModelPicker"

export default function GLDetector({ id, text: extractedText, onBack, onRunStart, onStream, onRunDone }) {
  const params = useParams()
  const docId = id || params.id
  // use API base from config (Vite env / runtime)
  const [prompt, setPrompt] = useState(`You are a Senior Accountant specialized in Chart of Accounts (COA) and automated document processing.

Task: Analyze the provided OCR text from a financial document (Invoice, Bill, or Receipt) and output the correct GL Code of the financial document.

Reference GL Code Library:

JSON:

{
  "200": "Sales / Revenue",
  "270": "Interest Income",
  "300": "Cost of Goods Sold (COGS)",
  "310": "Freight & Courier / Shipping",
  "320": "Customs & Import Duty",
  "400": "Advertising & Marketing",
  "410": "Bank Fees / Transaction Costs",
  "429": "General Expenses",
  "477": "Travel - International",
  "489": "IT Software & Cloud Services (e.g., AWS, SaaS)",
  "500": "Printing & Stationery",
  "720": "Computer Equipment (Asset)",
  "800": "Accounts Payable (System Account)",
  "820": "VAT/GST"
}

Instructions:
1. Identify the GL code of document.
2. Add explanations for all assumptions made during the detection process.
3. If GL code cannot be confidently detected, return "Unknown" as the GL Code. 
4. Return confidence level (0-100) for the assigned GL Code
5. Return list of keywords for RAG search to find similar documents. Do not include GL code or numbers in the keywords.
    `)
  const [text, setText] = useState("")
  // model picker (user-selectable). Default to an NVIDIA model identifier per request.
  const [model, setModel] = useState('nvidia/nemotron-3-super-120b-a12b:free')

  useEffect(() => {
    // prefer extractedText passed from parent; otherwise fetch by id so page works after refresh
    if (extractedText) {
      setText(extractedText)
      return
    }
    if (!docId) return
    let cancelled = false
    const fetchText = async () => {
      try {
        const res = await axios.get(`${API}/textract/${docId}`)
        if (!cancelled) setText(res.data.text || "")
      } catch (e) {
        if (!cancelled) setText("")
      }
    }
    fetchText()
    return () => { cancelled = true }
  }, [extractedText])
  const [loading, setLoading] = useState(false)

  const runDetection = () => {
    if (loading) return
    // open result page immediately
    if (onRunStart) onRunStart(model, docId)
    setLoading(true)

    try {
      const wsProtocol = API.startsWith('https') ? 'wss' : 'ws'
      const wsHost = API.replace(/^https?:\/\//, '')
      const ws = new WebSocket(`${wsProtocol}://${wsHost}/ws/detect_gl`)
      ws.onopen = () => {
        ws.send(JSON.stringify({ id: docId, prompt, model }))
      }
      ws.onmessage = (ev) => {
        const data = ev.data
        if (data === '[[DONE]]') {
          setLoading(false)
          try { ws.close() } catch (e) {}
          if (onRunDone) onRunDone()
          return
        }
        // pass chunks to parent to append to result
        if (onStream) onStream(data)
      }
      ws.onerror = (err) => {
        setLoading(false)
        alert('WebSocket error while streaming LLM output')
      }
      ws.onclose = () => {
        setLoading(false)
      }
    } catch (err) {
      setLoading(false)
      alert("Detection failed: " + (err?.message || err))
    }
  }

  return (
    <div>
      <div className="section-header-card" style={{ alignItems: 'center' }}>
        <div>
          <h2 className="section-title">GL Code Detector</h2>
          <p className="section-sub">Run a configurable agent prompt against the extracted text.</p>
          <p className="section-sub">Note that Agent Prompt is configurable and can be adjusted to improve detection accuracy. (RAG learning loop)</p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button className="btn-primary" onClick={runDetection} disabled={loading}>{loading ? 'Detecting…' : 'Detect GL Code'}</button>
          <button className="btn-primary" style={{ background: '#94a3b8' }} onClick={onBack}>Back</button>
        </div>
      </div>

          

      <div className="table-card" style={{ padding: 20, display: 'grid', gap: 12, maxHeight: '60vh', overflow: 'hidden' }}>
        <div>
          <h3 style={{ margin: '8px 0' }}>Agent Prompt (editable)</h3>
          <textarea value={prompt} onChange={e => setPrompt(e.target.value)} style={{ width: '100%', minHeight: 120, fontFamily: 'ui-monospace, "Fira Code", monospace', fontSize: 13, padding: 12, boxSizing: 'border-box' }} />
        </div>

        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <h3 style={{ margin: '8px 0' }}>Extracted Text</h3>
          <pre style={{ maxHeight: '55vh', whiteSpace: 'pre-wrap', fontFamily: 'ui-monospace, "Fira Code", monospace', fontSize: 11, color: '#0f172a', overflowY: 'auto', padding: 12, borderRadius: 8, background: '#fbfdff' }}>{text}</pre>
        </div>
      </div>

      <div className="table-card" style={{ padding: '12px 20px', marginTop: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1 }}>
            <ModelPicker
              model={model}
              onChange={setModel}
              disabled={false}
              datalistId="models"
              options={[
                'nvidia/nemotron-3-super-120b-a12b:free',
                'z-ai/glm-4.5-air:free',
                'qwen/qwen3-next-80b-a3b-instruct:free',
                'google/gemini-2.0-flash-lite-001',
              ]}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
