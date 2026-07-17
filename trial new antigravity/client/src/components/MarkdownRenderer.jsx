import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import './MarkdownRenderer.css'

const customDarkStyle = {
  ...oneDark,
  'pre[class*="language-"]': {
    ...oneDark['pre[class*="language-"]'],
    background: 'rgba(0, 0, 0, 0.4)',
    border: '1px solid rgba(255,255,255,0.06)',
    borderRadius: '10px',
    fontSize: '13px',
    fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
    margin: '12px 0',
  },
  'code[class*="language-"]': {
    ...oneDark['code[class*="language-"]'],
    fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
    fontSize: '13px',
  },
}

export default function MarkdownRenderer({ content, isStreaming }) {
  return (
    <div className={`markdown-body ${isStreaming ? 'typing-cursor' : ''}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ node, inline, className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || '')
            const lang = match ? match[1] : ''

            if (!inline && lang) {
              return (
                <div className="code-block-wrapper">
                  <div className="code-block-header">
                    <span className="code-lang">{lang}</span>
                    <button
                      className="copy-btn"
                      onClick={() => {
                        navigator.clipboard.writeText(String(children))
                        const btn = document.activeElement
                        const original = btn.textContent
                        btn.textContent = 'Copied!'
                        setTimeout(() => { btn.textContent = original }, 1500)
                      }}
                    >
                      Copy
                    </button>
                  </div>
                  <SyntaxHighlighter
                    style={customDarkStyle}
                    language={lang}
                    PreTag="div"
                    showLineNumbers={String(children).split('\n').length > 5}
                    {...props}
                  >
                    {String(children).replace(/\n$/, '')}
                  </SyntaxHighlighter>
                </div>
              )
            }

            return (
              <code className="inline-code" {...props}>
                {children}
              </code>
            )
          },
          h1: ({ children }) => <h1 className="md-h1">{children}</h1>,
          h2: ({ children }) => <h2 className="md-h2">{children}</h2>,
          h3: ({ children }) => <h3 className="md-h3">{children}</h3>,
          h4: ({ children }) => <h4 className="md-h4">{children}</h4>,
          p: ({ children }) => <p className="md-p">{children}</p>,
          ul: ({ children }) => <ul className="md-ul">{children}</ul>,
          ol: ({ children }) => <ol className="md-ol">{children}</ol>,
          li: ({ children }) => <li className="md-li">{children}</li>,
          blockquote: ({ children }) => <blockquote className="md-blockquote">{children}</blockquote>,
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer" className="md-link">{children}</a>
          ),
          table: ({ children }) => (
            <div className="md-table-wrapper">
              <table className="md-table">{children}</table>
            </div>
          ),
          th: ({ children }) => <th className="md-th">{children}</th>,
          td: ({ children }) => <td className="md-td">{children}</td>,
          hr: () => <hr className="md-hr" />,
          strong: ({ children }) => <strong className="md-strong">{children}</strong>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
