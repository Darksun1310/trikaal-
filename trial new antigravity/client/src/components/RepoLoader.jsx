import { useState } from 'react'
import './RepoLoader.css'

const EXAMPLE_REPOS = [
  'https://github.com/expressjs/express',
  'https://github.com/vitejs/vite',
  'https://github.com/axios/axios',
  'https://github.com/tailwindlabs/tailwindcss',
]

export default function RepoLoader({ apiKeys, setApiKeys, onLoaded }) {
  const [repoUrl, setRepoUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [loadingStage, setLoadingStage] = useState('')
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState('')
  const [showAdvanced, setShowAdvanced] = useState(false)

  async function handleLoad(e) {
    e.preventDefault()
    if (!repoUrl.trim()) return setError('Please enter a GitHub repository URL.')
    if (!apiKeys.gemini.trim()) return setError('Please enter your Gemini API key.')

    setError('')
    setLoading(true)
    setLoadingStage('Connecting to GitHub...')
    setProgress(10)

    try {
      // Fake staged progress for UX
      const progressTimer = setInterval(() => {
        setProgress(p => {
          if (p < 85) return p + Math.random() * 8
          return p
        })
      }, 800)

      setLoadingStage('Fetching repository files...')
      setProgress(20)

      const res = await fetch('/api/load-repo', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          repoUrl: repoUrl.trim(),
          githubToken: apiKeys.github.trim() || undefined,
          geminiApiKey: apiKeys.gemini.trim(),
        }),
      })

      clearInterval(progressTimer)
      setLoadingStage('Generating embeddings...')
      setProgress(90)

      const data = await res.json()
      if (!res.ok) throw new Error(data.error || 'Failed to load repository')

      setProgress(100)
      setLoadingStage('Ready!')

      await new Promise(r => setTimeout(r, 400))
      onLoaded({ ...data, repoUrl: repoUrl.trim() })
    } catch (err) {
      setError(err.message)
      setLoading(false)
      setProgress(0)
      setLoadingStage('')
    }
  }

  return (
    <div className="loader-page">
      <div className="loader-content fade-in">
        {/* Header */}
        <div className="loader-header">
          <div className="loader-logo">
            <div className="logo-icon">
              <svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
                <circle cx="16" cy="16" r="15" stroke="url(#grad)" strokeWidth="1.5"/>
                <path d="M10 22 C10 15, 22 15, 22 8" stroke="url(#grad2)" strokeWidth="2" strokeLinecap="round"/>
                <circle cx="22" cy="8" r="2.5" fill="#22d3ee"/>
                <circle cx="10" cy="22" r="2.5" fill="#8b5cf6"/>
                <circle cx="16" cy="15" r="2" fill="#a78bfa" opacity="0.8"/>
                <defs>
                  <linearGradient id="grad" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
                    <stop stopColor="#8b5cf6"/>
                    <stop offset="1" stopColor="#22d3ee"/>
                  </linearGradient>
                  <linearGradient id="grad2" x1="10" y1="22" x2="22" y2="8" gradientUnits="userSpaceOnUse">
                    <stop stopColor="#8b5cf6"/>
                    <stop offset="1" stopColor="#22d3ee"/>
                  </linearGradient>
                </defs>
              </svg>
            </div>
            <div className="logo-text">
              <h1>GitHub Codebase <span className="gradient-text">AI</span></h1>
              <p>Chat with any repository using RAG + Gemini</p>
            </div>
          </div>
        </div>

        {/* Features */}
        <div className="feature-pills">
          {[
            { icon: '🏗️', label: 'Architecture' },
            { icon: '📄', label: 'Documentation' },
            { icon: '🐛', label: 'Bug Detection' },
            { icon: '⚡', label: 'Improvements' },
            { icon: '💬', label: 'Q&A Chat' },
          ].map(f => (
            <div key={f.label} className="feature-pill">
              <span>{f.icon}</span>
              <span>{f.label}</span>
            </div>
          ))}
        </div>

        {/* Main Form */}
        <div className="loader-card glass">
          <form onSubmit={handleLoad} className="loader-form">
            {/* Gemini API Key */}
            <div className="form-group">
              <label htmlFor="gemini-key">
                <span className="label-icon">🔑</span>
                Gemini API Key
                <span className="label-required">required</span>
              </label>
              <input
                id="gemini-key"
                type="password"
                className="input"
                placeholder="AIza..."
                value={apiKeys.gemini}
                onChange={e => setApiKeys(k => ({ ...k, gemini: e.target.value }))}
                disabled={loading}
              />
              <span className="form-hint">
                Get your free key at{' '}
                <a href="https://aistudio.google.com/apikey" target="_blank" rel="noreferrer">
                  aistudio.google.com
                </a>
              </span>
            </div>

            {/* Repo URL */}
            <div className="form-group">
              <label htmlFor="repo-url">
                <span className="label-icon">
                  <svg viewBox="0 0 20 20" fill="currentColor" width="14" height="14">
                    <path fillRule="evenodd" d="M10 0C4.477 0 0 4.477 0 10c0 4.418 2.865 8.166 6.839 9.489.5.092.682-.217.682-.482 0-.237-.008-.866-.013-1.7-2.782.603-3.369-1.342-3.369-1.342-.454-1.155-1.11-1.462-1.11-1.462-.908-.62.069-.608.069-.608 1.003.07 1.531 1.03 1.531 1.03.892 1.529 2.341 1.087 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.11-4.555-4.943 0-1.091.39-1.984 1.029-2.683-.103-.253-.446-1.27.098-2.647 0 0 .84-.269 2.75 1.025A9.578 9.578 0 0110 4.836c.85.004 1.705.114 2.504.336 1.909-1.294 2.747-1.025 2.747-1.025.546 1.377.203 2.394.1 2.647.64.699 1.028 1.592 1.028 2.683 0 3.842-2.339 4.687-4.566 4.935.359.309.678.919.678 1.852 0 1.336-.012 2.415-.012 2.743 0 .267.18.578.688.48C17.137 18.163 20 14.418 20 10c0-5.523-4.477-10-10-10z" clipRule="evenodd"/>
                  </svg>
                </span>
                GitHub Repository URL
              </label>
              <input
                id="repo-url"
                type="text"
                className="input"
                placeholder="https://github.com/owner/repo"
                value={repoUrl}
                onChange={e => setRepoUrl(e.target.value)}
                disabled={loading}
              />
            </div>

            {/* Example repos */}
            <div className="example-repos">
              <span className="example-label">Try an example:</span>
              {EXAMPLE_REPOS.map(url => {
                const name = url.split('/').slice(-2).join('/')
                return (
                  <button
                    key={url}
                    type="button"
                    className="example-chip"
                    onClick={() => setRepoUrl(url)}
                    disabled={loading}
                  >
                    {name}
                  </button>
                )
              })}
            </div>

            {/* Advanced */}
            <div className="advanced-toggle">
              <button
                type="button"
                className="btn-ghost btn"
                style={{ fontSize: '12px', padding: '6px 12px' }}
                onClick={() => setShowAdvanced(v => !v)}
                disabled={loading}
              >
                <span>{showAdvanced ? '▲' : '▼'}</span>
                Advanced (GitHub Token for private repos)
              </button>
            </div>

            {showAdvanced && (
              <div className="form-group fade-in">
                <label htmlFor="github-token">
                  <span className="label-icon">🔐</span>
                  GitHub Personal Access Token
                  <span className="label-optional">optional</span>
                </label>
                <input
                  id="github-token"
                  type="password"
                  className="input"
                  placeholder="ghp_..."
                  value={apiKeys.github}
                  onChange={e => setApiKeys(k => ({ ...k, github: e.target.value }))}
                  disabled={loading}
                />
                <span className="form-hint">Required for private repositories</span>
              </div>
            )}

            {/* Error */}
            {error && (
              <div className="error-banner fade-in">
                <span>⚠️</span>
                <span>{error}</span>
              </div>
            )}

            {/* Loading progress */}
            {loading && (
              <div className="loading-state fade-in">
                <div className="loading-stage">
                  <div className="spinner" />
                  <span>{loadingStage}</span>
                </div>
                <div className="progress-bar">
                  <div
                    className="progress-fill"
                    style={{ width: `${progress}%` }}
                  />
                </div>
                <span className="progress-text">{Math.round(progress)}%</span>
              </div>
            )}

            {/* Submit */}
            <button
              id="load-repo-btn"
              type="submit"
              className="btn btn-primary load-btn"
              disabled={loading}
            >
              {loading ? (
                <>
                  <div className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }} />
                  Loading Repository...
                </>
              ) : (
                <>
                  <svg viewBox="0 0 20 20" fill="currentColor" width="16" height="16">
                    <path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z"/>
                  </svg>
                  Analyze Repository
                </>
              )}
            </button>
          </form>
        </div>

        {/* Footer info */}
        <div className="loader-footer">
          <div className="tech-badges">
            <span className="badge badge-purple">RAG</span>
            <span className="badge badge-cyan">Gemini 2.0</span>
            <span className="badge badge-green">Octokit</span>
            <span className="badge badge-purple">Vector Search</span>
          </div>
          <p>Powered by Gemini embeddings + cosine similarity retrieval</p>
        </div>
      </div>
    </div>
  )
}
