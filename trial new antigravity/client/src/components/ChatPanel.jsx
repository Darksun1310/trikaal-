import { useState, useRef, useEffect } from 'react'
import MarkdownRenderer from './MarkdownRenderer'
import './ChatPanel.css'

const SUGGESTED_QUESTIONS = [
  'Explain the overall architecture of this project',
  'What are the main entry points of this application?',
  'How is error handling implemented across the codebase?',
  'What design patterns are used here?',
  'Explain how authentication works in this repo',
  'What are the key data structures used?',
]

function Message({ msg }) {
  return (
    <div className={`message message-${msg.role} fade-in`}>
      <div className="message-avatar">
        {msg.role === 'user' ? '👤' : (
          <div className="ai-avatar">
            <svg viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" width="14" height="14">
              <circle cx="10" cy="10" r="9" stroke="url(#avatarGrad)" strokeWidth="1.5"/>
              <circle cx="10" cy="10" r="3" fill="url(#avatarGrad2)"/>
              <defs>
                <linearGradient id="avatarGrad" x1="0" y1="0" x2="20" y2="20" gradientUnits="userSpaceOnUse">
                  <stop stopColor="#8b5cf6"/><stop offset="1" stopColor="#22d3ee"/>
                </linearGradient>
                <linearGradient id="avatarGrad2" x1="0" y1="0" x2="20" y2="20" gradientUnits="userSpaceOnUse">
                  <stop stopColor="#8b5cf6"/><stop offset="1" stopColor="#22d3ee"/>
                </linearGradient>
              </defs>
            </svg>
          </div>
        )}
      </div>
      <div className="message-body">
        <div className="message-bubble">
          {msg.role === 'user' ? (
            <p className="user-text">{msg.content}</p>
          ) : (
            <MarkdownRenderer content={msg.content} isStreaming={msg.streaming} />
          )}
        </div>
        {msg.sources && msg.sources.length > 0 && (
          <div className="message-sources fade-in">
            <span className="sources-label">📎 Sources:</span>
            {msg.sources.map(s => (
              <span key={s} className="source-chip">{s}</span>
            ))}
          </div>
        )}
        {msg.error && (
          <div className="message-error">⚠️ {msg.error}</div>
        )}
      </div>
    </div>
  )
}

export default function ChatPanel({ repoState, apiKeys }) {
  const [messages, setMessages] = useState([
    {
      id: 0,
      role: 'assistant',
      content: `# Welcome! I've analyzed **${repoState.owner}/${repoState.repo}** 🎉\n\nI've loaded **${repoState.loadedFiles} files** and created **${repoState.chunks} semantic chunks** — ready to answer any question about this codebase.\n\nTry asking me about the architecture, specific functions, potential issues, or anything else!`,
      streaming: false,
    }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)
  const inputRef = useRef(null)
  const abortRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function sendMessage(text) {
    if (!text.trim() || loading) return

    const userMsg = { id: Date.now(), role: 'user', content: text }
    const aiMsg = { id: Date.now() + 1, role: 'assistant', content: '', streaming: true }

    setMessages(prev => [...prev, userMsg, aiMsg])
    setInput('')
    setLoading(true)

    // Build history (exclude the new AI message being streamed)
    const history = messages
      .filter(m => !m.streaming)
      .map(m => ({ role: m.role, content: m.content }))

    try {
      const controller = new AbortController()
      abortRef.current = controller

      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          repoUrl: repoState.repoUrl,
          geminiApiKey: apiKeys.gemini,
          message: text,
          history,
        }),
        signal: controller.signal,
      })

      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.error || 'Request failed')
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
              setMessages(prev => prev.map(m =>
                m.id === aiMsg.id ? { ...m, content: fullContent } : m
              ))
            }
            if (data.done) {
              sources = data.sources || []
            }
            if (data.error) {
              throw new Error(data.error)
            }
          } catch (parseErr) {
            // skip malformed lines
          }
        }
      }

      setMessages(prev => prev.map(m =>
        m.id === aiMsg.id ? { ...m, streaming: false, sources } : m
      ))
    } catch (err) {
      if (err.name === 'AbortError') return
      setMessages(prev => prev.map(m =>
        m.id === aiMsg.id
          ? { ...m, streaming: false, content: '', error: err.message }
          : m
      ))
    } finally {
      setLoading(false)
      abortRef.current = null
      inputRef.current?.focus()
    }
  }

  function handleSubmit(e) {
    e.preventDefault()
    sendMessage(input)
  }

  function handleStop() {
    abortRef.current?.abort()
    setLoading(false)
    setMessages(prev => prev.map(m => m.streaming ? { ...m, streaming: false } : m))
  }

  return (
    <div className="chat-panel">
      {/* Messages */}
      <div className="messages-container">
        {messages.map(msg => (
          <Message key={msg.id} msg={msg} />
        ))}
        {loading && messages[messages.length - 1]?.content === '' && (
          <div className="thinking-indicator fade-in">
            <div className="thinking-dots">
              <span />
              <span />
              <span />
            </div>
            <span className="thinking-text">Searching codebase...</span>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Suggested questions (shown when only welcome message) */}
      {messages.length === 1 && (
        <div className="suggestions fade-in">
          {SUGGESTED_QUESTIONS.slice(0, 4).map(q => (
            <button
              key={q}
              className="suggestion-chip"
              onClick={() => sendMessage(q)}
              disabled={loading}
            >
              {q}
            </button>
          ))}
        </div>
      )}

      {/* Input area */}
      <div className="chat-input-area">
        <form onSubmit={handleSubmit} className="chat-form">
          <div className="input-wrapper">
            <textarea
              ref={inputRef}
              id="chat-input"
              className="chat-textarea"
              placeholder={`Ask anything about ${repoState.owner}/${repoState.repo}...`}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  handleSubmit(e)
                }
              }}
              disabled={loading}
              rows={1}
            />
            {loading ? (
              <button
                type="button"
                id="stop-btn"
                className="send-btn stop-btn"
                onClick={handleStop}
                title="Stop generation"
              >
                <svg viewBox="0 0 16 16" fill="currentColor" width="14" height="14">
                  <rect x="3" y="3" width="10" height="10" rx="1"/>
                </svg>
              </button>
            ) : (
              <button
                type="submit"
                id="send-btn"
                className="send-btn"
                disabled={!input.trim()}
                title="Send (Enter)"
              >
                <svg viewBox="0 0 20 20" fill="currentColor" width="14" height="14">
                  <path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z"/>
                </svg>
              </button>
            )}
          </div>
          <p className="chat-hint">
            <kbd>Enter</kbd> to send · <kbd>Shift+Enter</kbd> for new line · RAG retrieves top 10 relevant chunks
          </p>
        </form>
      </div>
    </div>
  )
}
