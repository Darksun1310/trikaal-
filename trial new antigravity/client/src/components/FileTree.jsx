import { useState } from 'react'
import './FileTree.css'

const LANG_COLOR = {
  javascript: '#f7df1e',
  typescript: '#3178c6',
  python: '#3572a5',
  java: '#b07219',
  go: '#00add8',
  rust: '#dea584',
  c: '#555555',
  cpp: '#f34b7d',
  csharp: '#239120',
  ruby: '#701516',
  php: '#4f5d95',
  swift: '#f05138',
  kotlin: '#a97bff',
  html: '#e34c26',
  css: '#563d7c',
  scss: '#c6538c',
  json: '#ffa500',
  yaml: '#cb171e',
  markdown: '#083fa1',
  sql: '#e38c00',
  bash: '#89e051',
  vue: '#41b883',
  svelte: '#ff3e00',
  text: '#aaaaaa',
}

function getLangDot(lang) {
  return LANG_COLOR[lang] || '#aaaaaa'
}

function FileIcon({ language }) {
  const color = getLangDot(language)
  return (
    <span className="lang-dot" style={{ background: color }} title={language} />
  )
}

function TreeNode({ name, node, depth = 0 }) {
  const isFile = node && node._file
  const [open, setOpen] = useState(depth < 2)

  if (isFile) {
    return (
      <div className="tree-file" style={{ paddingLeft: `${depth * 14 + 8}px` }}>
        <FileIcon language={node.language} />
        <span className="tree-file-name" title={name}>{name}</span>
      </div>
    )
  }

  // Folder
  const children = Object.entries(node || {})
  return (
    <div className="tree-folder">
      <button
        className="tree-folder-btn"
        style={{ paddingLeft: `${depth * 14 + 8}px` }}
        onClick={() => setOpen(v => !v)}
      >
        <span className="folder-arrow">{open ? '▾' : '▸'}</span>
        <span className="folder-icon">{open ? '📂' : '📁'}</span>
        <span className="tree-folder-name">{name}</span>
      </button>
      {open && (
        <div className="tree-children">
          {children
            .sort(([, a], [, b]) => {
              const aIsFile = a?._file
              const bIsFile = b?._file
              if (aIsFile && !bIsFile) return 1
              if (!aIsFile && bIsFile) return -1
              return 0
            })
            .map(([childName, childNode]) => (
              <TreeNode
                key={childName}
                name={childName}
                node={childNode}
                depth={depth + 1}
              />
            ))}
        </div>
      )}
    </div>
  )
}

export default function FileTree({ fileTree, repoInfo, onReset }) {
  const [search, setSearch] = useState('')

  const totalFolders = countFolders(fileTree)

  return (
    <div className="file-tree">
      {/* Repo header */}
      <div className="tree-header">
        <div className="tree-repo-info">
          <svg viewBox="0 0 20 20" fill="currentColor" width="14" height="14" className="github-icon">
            <path fillRule="evenodd" d="M10 0C4.477 0 0 4.477 0 10c0 4.418 2.865 8.166 6.839 9.489.5.092.682-.217.682-.482 0-.237-.008-.866-.013-1.7-2.782.603-3.369-1.342-3.369-1.342-.454-1.155-1.11-1.462-1.11-1.462-.908-.62.069-.608.069-.608 1.003.07 1.531 1.03 1.531 1.03.892 1.529 2.341 1.087 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.11-4.555-4.943 0-1.091.39-1.984 1.029-2.683-.103-.253-.446-1.27.098-2.647 0 0 .84-.269 2.75 1.025A9.578 9.578 0 0110 4.836c.85.004 1.705.114 2.504.336 1.909-1.294 2.747-1.025 2.747-1.025.546 1.377.203 2.394.1 2.647.64.699 1.028 1.592 1.028 2.683 0 3.842-2.339 4.687-4.566 4.935.359.309.678.919.678 1.852 0 1.336-.012 2.415-.012 2.743 0 .267.18.578.688.48C17.137 18.163 20 14.418 20 10c0-5.523-4.477-10-10-10z" clipRule="evenodd"/>
          </svg>
          <span className="tree-repo-name">{repoInfo.owner}/{repoInfo.repo}</span>
        </div>
        <div className="tree-stats">
          <span className="badge badge-cyan">{repoInfo.branch}</span>
          <span className="tree-stat">{repoInfo.loadedFiles} files</span>
        </div>
        <button className="btn btn-ghost new-repo-btn" onClick={onReset} id="new-repo-btn">
          ← New Repo
        </button>
      </div>

      {/* Search */}
      <div className="tree-search">
        <input
          type="text"
          className="input"
          placeholder="Filter files..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ fontSize: '12px', padding: '7px 10px' }}
        />
      </div>

      {/* Tree */}
      <div className="tree-body">
        {search ? (
          <FlatSearch fileTree={fileTree} search={search} />
        ) : (
          Object.entries(fileTree)
            .sort(([, a], [, b]) => {
              const aIsFile = a?._file
              const bIsFile = b?._file
              if (aIsFile && !bIsFile) return 1
              if (!aIsFile && bIsFile) return -1
              return 0
            })
            .map(([name, node]) => (
              <TreeNode key={name} name={name} node={node} depth={0} />
            ))
        )}
      </div>
    </div>
  )
}

function FlatSearch({ fileTree, search }) {
  const files = []
  flattenTree(fileTree, '', files)
  const filtered = files.filter(f => f.path.toLowerCase().includes(search.toLowerCase()))

  return (
    <div>
      {filtered.slice(0, 50).map(f => (
        <div key={f.path} className="tree-file" style={{ paddingLeft: '8px' }}>
          <FileIcon language={f.language} />
          <span className="tree-file-name" title={f.path}>{f.path}</span>
        </div>
      ))}
      {filtered.length === 0 && (
        <div className="tree-empty">No files found</div>
      )}
    </div>
  )
}

function flattenTree(node, prefix, result) {
  for (const [name, child] of Object.entries(node)) {
    const path = prefix ? `${prefix}/${name}` : name
    if (child?._file) {
      result.push({ path, language: child.language })
    } else {
      flattenTree(child, path, result)
    }
  }
}

function countFolders(tree, count = 0) {
  for (const [, node] of Object.entries(tree)) {
    if (!node?._file) count = countFolders(node, count + 1)
  }
  return count
}
