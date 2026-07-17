import { useState } from 'react'
import RepoLoader from './components/RepoLoader'
import MainWorkspace from './components/MainWorkspace'
import './App.css'

export default function App() {
  const [repoState, setRepoState] = useState(null) // null = not loaded
  const [apiKeys, setApiKeys] = useState({ gemini: '', github: '' })

  function handleRepoLoaded(data) {
    setRepoState(data)
  }

  function handleReset() {
    setRepoState(null)
  }

  return (
    <div className="app">
      {/* Ambient background orbs */}
      <div className="bg-orb bg-orb-1" />
      <div className="bg-orb bg-orb-2" />
      <div className="bg-orb bg-orb-3" />

      {!repoState ? (
        <RepoLoader
          apiKeys={apiKeys}
          setApiKeys={setApiKeys}
          onLoaded={handleRepoLoaded}
        />
      ) : (
        <MainWorkspace
          repoState={repoState}
          apiKeys={apiKeys}
          onReset={handleReset}
        />
      )}
    </div>
  )
}
