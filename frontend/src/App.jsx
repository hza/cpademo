import React, { useState } from "react"
import { Routes, Route, useNavigate, useLocation } from "react-router-dom"
import Upload from "./components/Upload"
import ImageViewer from "./components/ImageViewer"
import GLDetector from "./components/GLDetector"
import GLResult from "./components/GLResult"
import Profile from "./components/Profile"

const NAV = [
  { section: "WORKSPACE", items: [
    { id: "documents",   label: "My Documents",   icon: "📄" },
  ]},
  { section: "ACCOUNT", items: [
    { id: "profile", label: "My Profile", icon: "👤" },
  ]},
]

export default function App() {
  const navigate = useNavigate()
  const location = useLocation()
  const [active, setActive] = useState("documents")
  const [viewerId, setViewerId] = useState(null)
  const [glId, setGlId] = useState(null)
  const [glText, setGlText] = useState("")
  const [glResult, setGlResult] = useState(null)
  const [glLoading, setGlLoading] = useState(false)
  const [glModel, setGlModel] = useState('')

  // keep `active` in sync with route for sidebar highlighting
  React.useEffect(() => {
    const path = location.pathname
    if (path.startsWith('/viewer')) setActive('viewer')
    else if (path.startsWith('/gl/') && path.endsWith('/result')) setActive('glResult')
    else if (path.startsWith('/gl')) setActive('gl')
    else if (path.startsWith('/profile')) setActive('profile')
    else setActive('documents')
  }, [location.pathname])

  const pageTitle = React.useMemo(() => {
    if (active === 'profile') return 'My Profile'
    // Treat image/gl pages as part of the Documents workspace
    return 'My Documents'
  }, [active])

  return (
    <div className="layout">
      {/* ── Sidebar ── */}
      <aside className="sidebar">
        <div className="sidebar-logo">
          <span className="logo-icon">📚</span>
          <span className="logo-text">CPA Demo</span>
        </div>
        <nav className="sidebar-nav">
          {NAV.map(group => (
            <div key={group.section} className="nav-group">
              <p className="nav-section-label">{group.section}</p>
              {group.items.map(item => (
                <button
                  key={item.id}
                  className={`nav-item${active === item.id ? " active" : ""}`}
                  onClick={() => {
                    // navigate based on id
                    if (item.id === 'documents') navigate('/')
                    else if (item.id === 'profile') navigate('/profile')
                    else navigate('/')
                  }}
                >
                  <span className="nav-icon">{item.icon}</span>
                  {item.label}
                </button>
              ))}
            </div>
          ))}
        </nav>
      </aside>

      {/* ── Main ── */}
      <div className="main-wrapper">
        {/* Header */}
        <header className="topbar">
          <h1 className="page-title">{pageTitle}</h1>
          <div className="topbar-right">
            <div className="search-box">
              <span className="search-icon">🔍</span>
              <input placeholder="Search documents…" />
            </div>
            <button className="icon-btn">🔔</button>
            <button className="icon-btn icon-btn--text">⚙</button>
            <div className="avatar">
              <span>JA</span>
              <div className="avatar-info">
                <span className="avatar-name">John Anderson</span>
                <span className="avatar-role">CPA</span>
              </div>
            </div>
          </div>
        </header>

        {/* Content */}
        <main className="content">
          <Routes>
            <Route path="/" element={<Upload onOpenViewer={(id) => { setViewerId(id); navigate(`/image/${id}`) }} />} />
              <Route path="/image/:id" element={<ImageViewer onBack={() => navigate(viewerId ? `/image/${viewerId}` : '/')} onDetectGL={(id, text) => { setGlId(id); setGlText(text || ''); navigate(`/gl/${id}`) }} />} />
            <Route path="/gl/:id" element={<GLDetector id={glId} text={glText} onBack={() => navigate(viewerId ? `/image/${viewerId}` : '/')} onRunStart={(model, id) => { setGlModel(model || ''); setGlResult(''); setGlId(id); setGlLoading(true); navigate(`/gl/${id}/result`) }} onStream={(chunk) => setGlResult(prev => prev + chunk)} onRunDone={() => setGlLoading(false)} />} />
            <Route path="/gl/:id/result" element={<GLResult result={glResult} loading={glLoading} model={glModel} onBack={() => navigate((glId ? `/gl/${glId}` : '/'))} />} />
            <Route path="/profile" element={<Profile />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}
