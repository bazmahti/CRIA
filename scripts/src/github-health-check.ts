import { execSync } from "node:child_process";

const GITHUB_TOKEN = process.env.GITHUB_TOKEN;

function run(cmd: string): string {
  return execSync(cmd, { encoding: "utf8" }).trim();
}

function getGitHubRemote(): { remote: string; owner: string; repo: string } | null {
  let remotes: string;
  try {
    remotes = run("git remote");
  } catch {
    return null;
  }

  for (const remote of remotes.split("\n").filter(Boolean)) {
    const url = run(`git remote get-url ${remote}`).trim();
    const match = url.match(/github\.com[/:]([\w.-]+)\/([\w.-]+?)(?:\.git)?$/);
    if (match) {
      return { remote, owner: match[1], repo: match[2] };
    }
  }
  return null;
}

async function getRemoteHeadSha(
  owner: string,
  repo: string,
  branch: string
): Promise<string | null> {
  if (!GITHUB_TOKEN) {
    console.error("[github-health-check] GITHUB_TOKEN is not set — cannot query GitHub API");
    return null;
  }

  const url = `https://api.github.com/repos/${owner}/${repo}/commits/${encodeURIComponent(branch)}`;
  const res = await fetch(url, {
    headers: {
      Authorization: `Bearer ${GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
    },
  });

  if (!res.ok) {
    const body = await res.text();
    console.error(`[github-health-check] GitHub API error ${res.status}: ${body}`);
    return null;
  }

  const data = (await res.json()) as { sha: string };
  return data.sha;
}

async function main() {
  const info = getGitHubRemote();
  if (!info) {
    console.log("[github-health-check] No GitHub remote found — skipping check");
    process.exit(0);
  }

  const { remote, owner, repo } = info;

  let localHead: string;
  try {
    localHead = run("git rev-parse HEAD");
  } catch {
    console.error("[github-health-check] Could not resolve local HEAD");
    process.exit(1);
  }

  const branch = run("git symbolic-ref --short HEAD 2>/dev/null || echo HEAD");

  console.log(`[github-health-check] Local  HEAD : ${localHead}`);
  console.log(`[github-health-check] Remote      : ${remote} (${owner}/${repo}@${branch})`);

  const remoteHead = await getRemoteHeadSha(owner, repo, branch);
  if (remoteHead === null) {
    console.error("[github-health-check] Could not fetch remote HEAD — sync status unknown");
    process.exit(1);
  }

  console.log(`[github-health-check] GitHub HEAD : ${remoteHead}`);

  if (localHead === remoteHead) {
    console.log("[github-health-check] OK — GitHub is in sync with local HEAD");
    process.exit(0);
  }

  console.error("");
  console.error("╔══════════════════════════════════════════════════════════════╗");
  console.error("║  GitHub sync DRIFT detected                                 ║");
  console.error("║  Local HEAD does not match the latest commit on GitHub.     ║");
  console.error("║  One or more pushes may have failed silently.               ║");
  console.error("╚══════════════════════════════════════════════════════════════╝");
  console.error("");
  console.error(`[github-health-check] local  : ${localHead}`);
  console.error(`[github-health-check] github : ${remoteHead}`);
  console.error("");
  process.exit(1);
}

main();
