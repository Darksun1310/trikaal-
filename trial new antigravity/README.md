# GitHub Codebase AI 🤖

> Chat with any GitHub repository using RAG + Gemini AI

Upload a GitHub repo and instantly get:
- 🏗️ **Architecture explanations** — understand how the codebase is structured
- 📄 **Auto-generated documentation** — README, API docs, and more
- 🐛 **Bug detection** — security vulnerabilities and code quality issues
- ⚡ **Improvement suggestions** — performance, maintainability, best practices
- 💬 **Q&A chat** — ask anything about the codebase in natural language

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Vite + React, Vanilla CSS (glassmorphism) |
| Backend | Node.js + Express |
| AI | Google Gemini 2.0 Flash |
| Embeddings | Gemini text-embedding-004 |
| RAG | In-memory vector store + cosine similarity |
| GitHub API | Octokit REST API |

## Quick Start

### Prerequisites
- Node.js 18+
- A [Gemini API key](https://aistudio.google.com/apikey) (free)

### Run

Double-click `start.bat` **or** run manually:

**Terminal 1 — Backend:**
```bash
cd server
npm install
node index.js
```

**Terminal 2 — Frontend:**
```bash
cd client
npm install
npm run dev
```

Then open **http://localhost:5173**

## How it Works

```
1. User enters GitHub URL + Gemini API key
2. Backend fetches all code files via Octokit Git Trees API
3. Files are chunked into ~80 line overlapping windows
4. Each chunk is embedded with Gemini text-embedding-004
5. Embeddings stored in memory (per session)
6. On each query:
   a. Query is embedded
   b. Top 10 chunks retrieved via cosine similarity
   c. Context + query sent to Gemini 2.0 Flash
   d. Response streamed back via SSE
```

## Limits

- Max 200 files per repo (prioritizes non-vendor files)
- Max 100KB per file
- In-memory store resets when server restarts
- Public repos only (add GitHub token for private)
