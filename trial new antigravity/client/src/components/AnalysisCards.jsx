import './AnalysisCards.css'

const ANALYSIS_TYPES = [
  {
    id: 'architecture',
    icon: '🏗️',
    label: 'Architecture',
    description: 'Understand the overall structure, design patterns, and how components interact',
    gradient: 'linear-gradient(135deg, #8b5cf6, #6366f1)',
    glow: 'rgba(139, 92, 246, 0.3)',
  },
  {
    id: 'documentation',
    icon: '📄',
    label: 'Generate Docs',
    description: 'Auto-generate comprehensive README and API documentation for the codebase',
    gradient: 'linear-gradient(135deg, #22d3ee, #06b6d4)',
    glow: 'rgba(34, 211, 238, 0.25)',
  },
  {
    id: 'bugs',
    icon: '🐛',
    label: 'Find Bugs',
    description: 'Detect potential bugs, security vulnerabilities, and code quality issues',
    gradient: 'linear-gradient(135deg, #ef4444, #ec4899)',
    glow: 'rgba(239, 68, 68, 0.25)',
  },
  {
    id: 'improvements',
    icon: '⚡',
    label: 'Improvements',
    description: 'Get actionable suggestions for performance, maintainability, and best practices',
    gradient: 'linear-gradient(135deg, #10b981, #22d3ee)',
    glow: 'rgba(16, 185, 129, 0.25)',
  },
]

export default function AnalysisCards({ onAnalyze, loading }) {
  return (
    <div className="analysis-section">
      <div className="analysis-header">
        <span className="analysis-title">Quick Analysis</span>
        <span className="analysis-subtitle">AI-powered deep dives</span>
      </div>
      <div className="analysis-grid">
        {ANALYSIS_TYPES.map(type => (
          <button
            key={type.id}
            id={`analyze-${type.id}-btn`}
            className="analysis-card"
            onClick={() => onAnalyze(type.id, type.label)}
            disabled={loading}
            style={{
              '--card-gradient': type.gradient,
              '--card-glow': type.glow,
            }}
          >
            <span className="analysis-card-icon">{type.icon}</span>
            <span className="analysis-card-label">{type.label}</span>
            <span className="analysis-card-desc">{type.description}</span>
          </button>
        ))}
      </div>
    </div>
  )
}
