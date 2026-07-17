import { useState } from 'react'
import FileTree from './FileTree'
import ChatPanel from './ChatPanel'
import AnalysisCards from './AnalysisCards'
import MarkdownRenderer from './MarkdownRenderer'
import './MainWorkspace.css'

export default function MainWorkspace({ repoState, apiKeys, onReset }) {
  const [loading, setLoading] = useState(false)
  const [analysisMessages, setAnalysisMessages] = useState([])
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [activePanel, setActivePanel] = useState('chat') // 'chat' | 'analysis'
  const [currentAnalysis, setCurrentAnalysis] = useState(null)

  async function handleAnalyze(type, label) {
    setActivePanel('analysis')
    setCurrentAnalysis({ type, label, content: '', streaming: true, sources: [] })
    setLoading(true)

    try {
      const res = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          repoUrl: repoState.repoUrl,
          geminiApiKey: apiKeys.gemini,
          type,
        }),
      })

      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.error || 'Analysis failed')
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let fullContent = ''
      let sources = []

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const data = JSON.parse(line.slice(6))
            if (data.text) {
              fullContent += data.text
              setCurrentAnalysis(prev => ({ ...prev, content: fullContent }))
            }
            if (data.done) sources = data.sources || []
          } catch {}
        }
      }

      setCurrentAnalysis(prev => ({ ...prev, streaming: false, sources }))
    } catch (err) {
      setCurrentAnalysis(prev => ({ ...prev, streaming: false, error: err.message }))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="workspace">
      {/* Top bar */}
      <header className="workspace-header">
        <div className="header-left">
          <button
            className="sidebar-toggle"
            onClick={() => setSidebarOpen(v => !v)}
            id="sidebar-toggle-btn"
            title="Toggle file tree"
          >
            <svg viewBox="0 0 20 20" fill="currentColor" width="16" height="16">
              <path fillRule="evenodd" d="M3 5a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 10a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 15a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z" clipRule="evenodd"/>
            </svg>
          </button>
          <div className="header-brand">
            <span className="header-logo-dot" />
            <span className="header-title gradient-text">GitHub Codebase AI</span>
          </div>
          <div className="header-repo-badge">
            <svg viewBox="0 0 16 16" fill="currentColor" width="12" height="12" opacity="0.6">
              <path fillRule="evenodd" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" clipRule="evenodd"/>
            </svg>
            <span>{repoState.owner}/{repoState.repo}</span>
            <span className="badge badge-cyan" style={{ fontSize: '10px' }}>{repoState.branch}</span>
          </div>
        </div>

        <div className="header-center">
          <div className="tab-group">
            <button
              id="tab-chat"
              className={`tab-btn ${activePanel === 'chat' ? 'active' : ''}`}
              onClick={() => setActivePanel('chat')}
            >
              💬 Chat
            </button>
            <button
              id="tab-analysis"
              className={`tab-btn ${activePanel === 'analysis' ? 'active' : ''}`}
              onClick={() => setActivePanel('analysis')}
            >
              🔬 Analysis
              {currentAnalysis && <span className="tab-dot" />}
            </button>
          </div>
        </div>

        <div className="header-right">
          <div className="header-stats">
            <span className="stat-item">
              <span className="stat-dot stat-green" />
              {repoState.loadedFiles} files
            </span>
            <span className="stat-item">
              <span className="stat-dot stat-purple" />
              {repoState.chunks} chunks
            </span>
          </div>
        </div>
      </header>

      {/* Main content */}
      <div className="workspace-body">
        {/* Sidebar */}
        <aside className={`workspace-sidebar ${sidebarOpen ? 'open' : 'closed'}`}>
          <div className="sidebar-content">
            <FileTree
              fileTree={repoState.fileTree}
              repoInfo={repoState}
              onReset={onReset}
            />
            <AnalysisCards onAnalyze={handleAnalyze} loading={loading} />
          </div>
        </aside>

        {/* Main panel */}
        <main className="workspace-main">
          {activePanel === 'chat' ? (
            <ChatPanel repoState={repoState} apiKeys={apiKeys} />
          ) : (
            <AnalysisPanel analysis={currentAnalysis} onBack={() => setActivePanel('chat')} />
          )}
        </main>
      </div>
    </div>
  )
}

function AnalysisPanel({ analysis, onBack }) {

  if (!analysis) {
    return (
      <div className="analysis-empty">
        <div className="analysis-empty-icon">🔬</div>
        <h2>No Analysis Yet</h2>
        <p>Click one of the analysis cards in the sidebar to get started.</p>
        <button className="btn btn-ghost" onClick={onBack}>← Back to Chat</button>
      </div>
    )
  }

  return (
    <div className="analysis-panel">
      <div className="analysis-panel-header">
        <button className="btn btn-ghost" onClick={onBack} id="back-to-chat-btn">
          ← Chat
        </button>
        <h2 className="analysis-panel-title">
          {analysis.type === 'architecture' && '🏗️ Architecture Overview'}
          {analysis.type === 'documentation' && '📄 Generated Documentation'}
          {analysis.type === 'bugs' && '🐛 Bug Report'}
          {analysis.type === 'improvements' && '⚡ Improvement Suggestions'}
        </h2>
        {analysis.streaming && (
          <div className="spinner" style={{ width: 16, height: 16 }} />
        )}
      </div>

      <div className="analysis-panel-body">
        {analysis.content ? (
          <MarkdownRenderer content={analysis.content} isStreaming={analysis.streaming} />
        ) : (
          <div className="analysis-loading">
            <div className="thinking-dots-lg">
              <span /><span /><span />
            </div>
            <p>Analyzing codebase...</p>
          </div>
        )}

        {analysis.error && (
          <div className="error-banner fade-in">
            <span>⚠️</span>
            <span>{analysis.error}</span>
          </div>
        )}

        {!analysis.streaming && analysis.sources?.length > 0 && (
          <div className="analysis-sources fade-in">
            <h4>📎 Files Referenced</h4>
            <div className="analysis-source-list">
              {analysis.sources.map(s => (
                <span key={s} className="source-chip">{s}</span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
