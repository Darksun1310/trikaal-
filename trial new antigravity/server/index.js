import "dotenv/config";
import express from "express";
import cors from "cors";
import { GoogleGenerativeAI } from "@google/generative-ai";
import { fetchRepo } from "./github.js";
import { chunkFiles, embedChunks, retrieveContext, buildContext } from "./rag.js";

const app = express();
app.use(cors());
app.use(express.json({ limit: "10mb" }));

const PORT = process.env.PORT || 3001;

// In-memory store: one repo per session (keyed by API key + repo URL for simplicity)
const repoStore = new Map();

function getStoreKey(apiKey, repoUrl) {
  return `${apiKey}::${repoUrl}`;
}

// ─── POST /api/load-repo ───────────────────────────────────────────────────
app.post("/api/load-repo", async (req, res) => {
  const { repoUrl, githubToken, geminiApiKey } = req.body;

  if (!repoUrl) return res.status(400).json({ error: "repoUrl is required" });
  if (!geminiApiKey) return res.status(400).json({ error: "Gemini API key is required" });

  try {
    // Send progress via streaming response
    res.setHeader("Content-Type", "application/json");

    console.log(`[load-repo] Fetching ${repoUrl}...`);
    const repoData = await fetchRepo(repoUrl, githubToken);
    console.log(`[load-repo] Got ${repoData.files.length} files. Chunking...`);

    const chunks = chunkFiles(repoData.files);
    console.log(`[load-repo] ${chunks.length} chunks. Embedding...`);

    const embeddedChunks = await embedChunks(chunks, geminiApiKey);
    console.log(`[load-repo] Embedded ${embeddedChunks.length} chunks. Done.`);

    const storeKey = getStoreKey(geminiApiKey, repoUrl);
    repoStore.set(storeKey, {
      repoData,
      embeddedChunks,
      loadedAt: new Date().toISOString(),
    });

    res.json({
      success: true,
      owner: repoData.owner,
      repo: repoData.repo,
      branch: repoData.defaultBranch,
      totalFiles: repoData.totalFiles,
      loadedFiles: repoData.loadedFiles,
      chunks: embeddedChunks.length,
      fileTree: buildFileTree(repoData.files),
    });
  } catch (err) {
    console.error("[load-repo] Error:", err.message);
    res.status(500).json({ error: err.message });
  }
});

// ─── POST /api/chat ────────────────────────────────────────────────────────
app.post("/api/chat", async (req, res) => {
  const { repoUrl, geminiApiKey, message, history = [] } = req.body;

  if (!repoUrl || !geminiApiKey || !message) {
    return res.status(400).json({ error: "repoUrl, geminiApiKey, and message are required" });
  }

  const storeKey = getStoreKey(geminiApiKey, repoUrl);
  const stored = repoStore.get(storeKey);
  if (!stored) {
    return res.status(404).json({ error: "Repository not loaded. Please load a repo first." });
  }

  try {
    const { embeddedChunks, repoData } = stored;

    // RAG: retrieve relevant context
    const relevant = await retrieveContext(message, embeddedChunks, geminiApiKey, 10);
    const context = buildContext(relevant);

    const genAI = new GoogleGenerativeAI(geminiApiKey);
    const model = genAI.getGenerativeModel({
      model: "gemini-2.0-flash",
      systemInstruction: `You are an expert code analyst AI assistant for the GitHub repository "${repoData.owner}/${repoData.repo}".

You have access to the codebase context provided below. Use it to answer questions accurately.

Guidelines:
- Be specific and reference actual file paths and line numbers when possible
- Format code blocks with appropriate language tags
- Be concise but thorough
- If you don't have enough context to answer confidently, say so
- When explaining architecture, describe how components interact
- When finding bugs, explain why it's a bug and suggest fixes

Repository: ${repoData.owner}/${repoData.repo} (${repoData.defaultBranch} branch)
Total files loaded: ${repoData.loadedFiles}`,
    });

    // Stream the response
    res.setHeader("Content-Type", "text/event-stream");
    res.setHeader("Cache-Control", "no-cache");
    res.setHeader("Connection", "keep-alive");

    const chatHistory = history.map(h => ({
      role: h.role,
      parts: [{ text: h.content }],
    }));

    const chat = model.startChat({ history: chatHistory });

    const prompt = `## Relevant Code Context\n\n${context}\n\n## Question\n\n${message}`;

    const streamResult = await chat.sendMessageStream(prompt);

    let fullText = "";
    for await (const chunk of streamResult.stream) {
      const text = chunk.text();
      fullText += text;
      res.write(`data: ${JSON.stringify({ text })}\n\n`);
    }

    // Send sources
    const sources = [...new Set(relevant.map(c => c.path))];
    res.write(`data: ${JSON.stringify({ done: true, sources })}\n\n`);
    res.end();
  } catch (err) {
    console.error("[chat] Error:", err.message);
    if (!res.headersSent) {
      res.status(500).json({ error: err.message });
    } else {
      res.write(`data: ${JSON.stringify({ error: err.message })}\n\n`);
      res.end();
    }
  }
});

// ─── POST /api/analyze ────────────────────────────────────────────────────
app.post("/api/analyze", async (req, res) => {
  const { repoUrl, geminiApiKey, type } = req.body;

  const ANALYSIS_PROMPTS = {
    architecture: "Provide a comprehensive architecture overview of this codebase. Describe: 1) The overall structure and design patterns used, 2) Key modules/components and their responsibilities, 3) How data flows through the system, 4) External dependencies and integrations, 5) Entry points. Use a tree diagram if helpful.",
    documentation: "Generate comprehensive documentation for this codebase. Include: 1) Project overview and purpose, 2) Installation and setup instructions, 3) Key API/function documentation with parameters and return values, 4) Usage examples, 5) Configuration options. Format as proper Markdown documentation.",
    bugs: "Analyze this codebase for potential bugs, security vulnerabilities, and code quality issues. For each issue found: 1) Describe the problem clearly, 2) Reference the specific file and approximate location, 3) Explain why it's problematic, 4) Provide a suggested fix. Prioritize by severity (Critical > High > Medium > Low).",
    improvements: "Suggest concrete improvements for this codebase. Cover: 1) Performance optimizations, 2) Code organization and maintainability, 3) Missing error handling, 4) Testing gaps, 5) Modern patterns or practices that could be adopted. Be specific with examples from the actual code.",
  };

  const prompt = ANALYSIS_PROMPTS[type];
  if (!prompt) return res.status(400).json({ error: "Invalid analysis type" });

  const storeKey = getStoreKey(geminiApiKey, repoUrl);
  const stored = repoStore.get(storeKey);
  if (!stored) return res.status(404).json({ error: "Repository not loaded." });

  try {
    const { embeddedChunks, repoData } = stored;

    // For analysis, grab a broad sample of the codebase
    const relevant = await retrieveContext(prompt, embeddedChunks, geminiApiKey, 15);
    const context = buildContext(relevant);

    const genAI = new GoogleGenerativeAI(geminiApiKey);
    const model = genAI.getGenerativeModel({
      model: "gemini-2.0-flash",
      systemInstruction: `You are an expert software engineer analyzing the GitHub repository "${repoData.owner}/${repoData.repo}". Provide detailed, actionable analysis based on the code context provided.`,
    });

    res.setHeader("Content-Type", "text/event-stream");
    res.setHeader("Cache-Control", "no-cache");
    res.setHeader("Connection", "keep-alive");

    const fullPrompt = `## Codebase Context\n\n${context}\n\n## Task\n\n${prompt}`;
    const streamResult = await model.generateContentStream(fullPrompt);

    for await (const chunk of streamResult.stream) {
      const text = chunk.text();
      res.write(`data: ${JSON.stringify({ text })}\n\n`);
    }

    const sources = [...new Set(relevant.map(c => c.path))];
    res.write(`data: ${JSON.stringify({ done: true, sources })}\n\n`);
    res.end();
  } catch (err) {
    console.error("[analyze] Error:", err.message);
    if (!res.headersSent) {
      res.status(500).json({ error: err.message });
    } else {
      res.write(`data: ${JSON.stringify({ error: err.message })}\n\n`);
      res.end();
    }
  }
});

// ─── GET /api/health ──────────────────────────────────────────────────────
app.get("/api/health", (_, res) => res.json({ ok: true }));

// ─── Helpers ──────────────────────────────────────────────────────────────
function buildFileTree(files) {
  const tree = {};
  for (const file of files) {
    const parts = file.path.split("/");
    let node = tree;
    for (let i = 0; i < parts.length - 1; i++) {
      if (!node[parts[i]]) node[parts[i]] = {};
      node = node[parts[i]];
    }
    node[parts[parts.length - 1]] = { _file: true, language: file.language, size: file.size };
  }
  return tree;
}

app.listen(PORT, () => {
  console.log(`🚀 GitHub Codebase AI server running on http://localhost:${PORT}`);
});
