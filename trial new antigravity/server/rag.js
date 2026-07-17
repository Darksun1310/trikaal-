import { GoogleGenerativeAI } from "@google/generative-ai";

const CHUNK_SIZE = 80; // lines per chunk
const CHUNK_OVERLAP = 10;

/**
 * Split files into overlapping chunks with metadata
 */
export function chunkFiles(files) {
  const chunks = [];
  
  for (const file of files) {
    const lines = file.content.split("\n");
    
    if (lines.length <= CHUNK_SIZE) {
      // Small file — keep as single chunk
      chunks.push({
        id: chunks.length,
        path: file.path,
        language: file.language,
        content: file.content,
        startLine: 1,
        endLine: lines.length,
        text: `File: ${file.path}\n\`\`\`${file.language}\n${file.content}\n\`\`\``,
      });
    } else {
      // Large file — split into overlapping chunks
      for (let start = 0; start < lines.length; start += CHUNK_SIZE - CHUNK_OVERLAP) {
        const end = Math.min(start + CHUNK_SIZE, lines.length);
        const chunkLines = lines.slice(start, end);
        chunks.push({
          id: chunks.length,
          path: file.path,
          language: file.language,
          content: chunkLines.join("\n"),
          startLine: start + 1,
          endLine: end,
          text: `File: ${file.path} (lines ${start + 1}-${end})\n\`\`\`${file.language}\n${chunkLines.join("\n")}\n\`\`\``,
        });
        if (end === lines.length) break;
      }
    }
  }
  
  return chunks;
}

/**
 * Embed all chunks using Gemini embedding model
 */
export async function embedChunks(chunks, apiKey) {
  const genAI = new GoogleGenerativeAI(apiKey);
  const model = genAI.getGenerativeModel({ model: "text-embedding-004" });
  
  const EMBED_BATCH = 20;
  const embedded = [];
  
  for (let i = 0; i < chunks.length; i += EMBED_BATCH) {
    const batch = chunks.slice(i, i + EMBED_BATCH);
    const results = await Promise.allSettled(
      batch.map(async (chunk) => {
        const result = await model.embedContent(chunk.text.slice(0, 8000));
        return {
          ...chunk,
          embedding: result.embedding.values,
        };
      })
    );
    
    for (const r of results) {
      if (r.status === "fulfilled") {
        embedded.push(r.value);
      }
    }
    
    // Small delay to respect rate limits
    if (i + EMBED_BATCH < chunks.length) {
      await new Promise(r => setTimeout(r, 200));
    }
  }
  
  return embedded;
}

/**
 * Cosine similarity between two vectors
 */
function cosineSimilarity(a, b) {
  let dot = 0, normA = 0, normB = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }
  return dot / (Math.sqrt(normA) * Math.sqrt(normB));
}

/**
 * Retrieve top-K most relevant chunks for a query
 */
export async function retrieveContext(query, embeddedChunks, apiKey, k = 8) {
  const genAI = new GoogleGenerativeAI(apiKey);
  const model = genAI.getGenerativeModel({ model: "text-embedding-004" });
  
  const result = await model.embedContent(query);
  const queryEmbedding = result.embedding.values;
  
  const scored = embeddedChunks.map(chunk => ({
    ...chunk,
    score: cosineSimilarity(queryEmbedding, chunk.embedding),
  }));
  
  scored.sort((a, b) => b.score - a.score);
  return scored.slice(0, k);
}

/**
 * Build a structured context string from retrieved chunks
 * Deduplicates by file path
 */
export function buildContext(chunks) {
  // Group by file
  const byFile = {};
  for (const chunk of chunks) {
    if (!byFile[chunk.path]) byFile[chunk.path] = [];
    byFile[chunk.path].push(chunk);
  }
  
  const parts = [];
  for (const [path, fileChunks] of Object.entries(byFile)) {
    const combined = fileChunks.map(c => c.content).join("\n...\n");
    parts.push(`### ${path}\n\`\`\`${fileChunks[0].language}\n${combined}\n\`\`\``);
  }
  
  return parts.join("\n\n");
}
