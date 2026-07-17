import { Octokit } from "@octokit/rest";

// File extensions we care about
const CODE_EXTENSIONS = new Set([
  ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
  ".py", ".pyw",
  ".java", ".kt", ".kts",
  ".go",
  ".rs",
  ".c", ".cpp", ".cc", ".h", ".hpp",
  ".cs",
  ".rb",
  ".php",
  ".swift",
  ".scala",
  ".r", ".R",
  ".sh", ".bash", ".zsh",
  ".html", ".htm",
  ".css", ".scss", ".sass", ".less",
  ".json", ".yaml", ".yml", ".toml",
  ".md", ".mdx", ".txt", ".rst",
  ".sql",
  ".vue", ".svelte",
  ".env.example", ".gitignore", ".dockerfile",
  "dockerfile", "makefile", "rakefile"
]);

const MAX_FILES = 200;
const MAX_FILE_SIZE = 100 * 1024; // 100 KB per file

function getExtension(filename) {
  const lower = filename.toLowerCase();
  const dotIdx = lower.lastIndexOf(".");
  if (dotIdx === -1) return lower; // no extension, check full name
  return lower.slice(dotIdx);
}

function isCodeFile(filename) {
  const ext = getExtension(filename);
  // Check common no-extension files
  const base = filename.toLowerCase();
  if (["dockerfile", "makefile", "rakefile", "procfile", "gemfile"].includes(base)) return true;
  return CODE_EXTENSIONS.has(ext);
}

/**
 * Parse a GitHub URL into { owner, repo }
 */
export function parseGithubUrl(url) {
  try {
    const u = new URL(url.trim());
    const parts = u.pathname.replace(/^\//, "").replace(/\/$/, "").split("/");
    if (parts.length < 2) throw new Error("Invalid URL");
    return { owner: parts[0], repo: parts[1] };
  } catch {
    // Try plain "owner/repo" format
    const parts = url.trim().split("/");
    if (parts.length >= 2) {
      return { owner: parts[0], repo: parts[1] };
    }
    throw new Error("Invalid GitHub URL. Use https://github.com/owner/repo");
  }
}

/**
 * Recursively fetch all files from a GitHub repo using the Git Trees API
 */
export async function fetchRepo(url, githubToken) {
  const { owner, repo } = parseGithubUrl(url);

  const octokit = new Octokit({
    auth: githubToken || undefined,
    userAgent: "github-codebase-ai/1.0",
  });

  // Get the default branch
  let defaultBranch = "main";
  try {
    const { data: repoData } = await octokit.repos.get({ owner, repo });
    defaultBranch = repoData.default_branch;
  } catch (e) {
    if (e.status === 404) throw new Error("Repository not found. Check the URL or add a GitHub token for private repos.");
    if (e.status === 403) throw new Error("Rate limited or access denied. Add a GitHub token.");
    throw e;
  }

  // Get the full file tree (recursive)
  const { data: treeData } = await octokit.git.getTree({
    owner,
    repo,
    tree_sha: defaultBranch,
    recursive: "1",
  });

  // Filter to code files only
  const codeFiles = treeData.tree.filter(
    (item) => item.type === "blob" && isCodeFile(item.path) && item.size <= MAX_FILE_SIZE
  );

  if (codeFiles.length === 0) {
    throw new Error("No code files found in this repository.");
  }

  // Cap at MAX_FILES, prioritizing non-test, non-vendor files
  const prioritized = codeFiles
    .filter(f => !f.path.includes("node_modules") && !f.path.includes("vendor") && !f.path.includes(".git"))
    .slice(0, MAX_FILES);

  // Fetch file contents in batches
  const BATCH_SIZE = 10;
  const files = [];
  
  for (let i = 0; i < prioritized.length; i += BATCH_SIZE) {
    const batch = prioritized.slice(i, i + BATCH_SIZE);
    const results = await Promise.allSettled(
      batch.map(async (file) => {
        const { data } = await octokit.git.getBlob({
          owner,
          repo,
          file_sha: file.sha,
        });
        const content = Buffer.from(data.content, "base64").toString("utf-8");
        return {
          path: file.path,
          content,
          size: file.size,
          language: getLanguage(file.path),
        };
      })
    );
    
    for (const result of results) {
      if (result.status === "fulfilled") {
        files.push(result.value);
      }
    }
  }

  return {
    owner,
    repo,
    defaultBranch,
    totalFiles: treeData.tree.filter(i => i.type === "blob").length,
    loadedFiles: files.length,
    files,
  };
}

function getLanguage(path) {
  const ext = getExtension(path);
  const map = {
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".py": "python", ".pyw": "python",
    ".java": "java",
    ".kt": "kotlin", ".kts": "kotlin",
    ".go": "go",
    ".rs": "rust",
    ".c": "c", ".h": "c",
    ".cpp": "cpp", ".cc": "cpp", ".hpp": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".scala": "scala",
    ".sh": "bash", ".bash": "bash", ".zsh": "bash",
    ".html": "html", ".htm": "html",
    ".css": "css", ".scss": "scss", ".sass": "scss", ".less": "less",
    ".json": "json",
    ".yaml": "yaml", ".yml": "yaml",
    ".toml": "toml",
    ".md": "markdown", ".mdx": "markdown",
    ".sql": "sql",
    ".vue": "vue",
    ".svelte": "svelte",
  };
  return map[ext] || "text";
}
