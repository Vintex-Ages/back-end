import fs from 'node:fs';
import { decideCloseAction, parseClosingIssueNumbers } from './lib/closing-issues.mjs';
import { createProjectStatusClient } from './lib/project-status.mjs';

const token = process.env.GH_TOKEN;
const [owner, repo] = process.env.GITHUB_REPOSITORY.split('/');
const org = process.env.PROJECT_ORG;
const sourceProjectNumber = Number(process.env.SOURCE_PROJECT_NUMBER);
const aggregateProjectNumber = Number(process.env.AGGREGATE_PROJECT_NUMBER);
const dryRun = process.env.DRY_RUN === 'true';
const issueNumberOverride = process.env.ISSUE_NUMBER_OVERRIDE;

const api = async (path, options = {}) => {
  const response = await fetch(`https://api.github.com${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    throw new Error(`${options.method || 'GET'} ${path}: ${response.status} ${await response.text()}`);
  }
  return response.status === 204 ? null : response.json();
};

const graphql = async (query, variables) => {
  const data = await api('/graphql', {
    method: 'POST',
    body: JSON.stringify({ query, variables }),
    headers: { 'Content-Type': 'application/json' },
  });
  if (data.errors) throw new Error(JSON.stringify(data.errors));
  return data.data;
};

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function nativeReferencingPRs(issueNumber) {
  const data = await graphql(
    `
      query ($owner: String!, $repo: String!, $number: Int!) {
        repository(owner: $owner, name: $repo) {
          issue(number: $number) {
            id
            closedByPullRequestsReferences(first: 50, includeClosedPrs: true) {
              nodes { number state }
            }
          }
        }
      }
    `,
    { owner, repo, number: issueNumber },
  );
  const issue = data.repository.issue;
  return { issueId: issue.id, prs: issue.closedByPullRequestsReferences.nodes };
}

async function textSearchReferencingPRs(issueNumber) {
  // Fallback signal: don't rely solely on the native Development link, which
  // this sprint is only populated by link-backfill.mjs (PRs target `develop`,
  // not the repo's default branch, so GitHub itself never auto-populates it).
  const query = encodeURIComponent(`repo:${owner}/${repo} type:pr in:body #${issueNumber}`);
  const results = await api(`/search/issues?q=${query}&per_page=50`).catch(() => ({ items: [] }));

  const referencing = [];
  for (const candidate of results.items ?? []) {
    const full = await api(`/repos/${owner}/${repo}/pulls/${candidate.number}`).catch(() => null);
    if (!full) continue;
    // The search API matches any mention of the number — only count it if the
    // body actually has a real Closes/Fixes/Resolves reference to this issue.
    if (parseClosingIssueNumbers(full.body).includes(issueNumber)) {
      referencing.push({ number: full.number, state: full.merged ? 'MERGED' : full.state.toUpperCase() });
    }
  }
  return referencing;
}

function dedupeByNumber(prs) {
  const seen = new Map();
  for (const pr of prs) seen.set(pr.number, pr);
  return [...seen.values()];
}

async function guardIssue(issueNumber) {
  const issue = await api(`/repos/${owner}/${repo}/issues/${issueNumber}`);
  if (issue.state !== 'closed') {
    console.log(`Issue #${issueNumber} não está fechada, nada a fazer.`);
    return;
  }

  const { issueId, prs: nativePRs } = await nativeReferencingPRs(issueNumber);
  const textPRs = await textSearchReferencingPRs(issueNumber);
  const allPRs = dedupeByNumber([...nativePRs, ...textPRs]);

  const decision = decideCloseAction(allPRs);
  if (decision.action === 'allow') {
    console.log(`Issue #${issueNumber}: allow (${decision.reason}).`);
    return;
  }

  const openList = decision.open.map((pr) => `#${pr.number}`).join(', ');
  if (dryRun) {
    console.log(`[dry-run] reabriria a issue #${issueNumber}; PRs abertas: ${openList}`);
    return;
  }

  // Snapshot Status on both boards BEFORE reopening — defense against the
  // native Project workflow rules ("Item closed" / "Auto-close issue") that
  // may still react to this same event.
  const projectStatus = createProjectStatusClient({ token, org });
  const statusBefore = {};
  for (const number of [sourceProjectNumber, aggregateProjectNumber]) {
    statusBefore[number] = await projectStatus.readStatus(number, issueId).catch(() => null);
  }

  await api(`/repos/${owner}/${repo}/issues/${issueNumber}`, {
    method: 'PATCH',
    body: JSON.stringify({ state: 'open', state_reason: 'reopened' }),
    headers: { 'Content-Type': 'application/json' },
  });
  await api(`/repos/${owner}/${repo}/issues/${issueNumber}/comments`, {
    method: 'POST',
    body: JSON.stringify({
      body:
        'Esta issue foi reaberta automaticamente: o fechamento é efeito exclusivo do merge da PR ' +
        'vinculada em `develop` (feito pelo pr-lifecycle). PR(s) ainda aberta(s) referenciando esta ' +
        `issue: ${openList}. Não é necessário fechá-la manualmente — isso acontece sozinho quando a ` +
        'PR for mesclada.',
    }),
    headers: { 'Content-Type': 'application/json' },
  });
  console.log(`Issue #${issueNumber} reaberta; PRs abertas: ${openList}.`);

  // Give any native Project workflow rule a moment to react to the reopen
  // before we correct the Status back — otherwise we could write first and
  // have the native rule immediately overwrite us again.
  await sleep(3000);

  for (const number of [sourceProjectNumber, aggregateProjectNumber]) {
    const before = statusBefore[number];
    if (!before) continue;
    const after = await projectStatus.readStatus(number, issueId).catch(() => null);
    if (after !== before) {
      await projectStatus.setStatus(number, issueId, before);
      console.log(`Status restaurado no Project ${number}: "${after}" -> "${before}".`);
    }
  }
}

if (issueNumberOverride) {
  await guardIssue(Number(issueNumberOverride));
} else {
  const event = JSON.parse(fs.readFileSync(process.env.GITHUB_EVENT_PATH, 'utf8'));
  if (event.action === 'closed' && event.issue) {
    await guardIssue(event.issue.number);
  }
}
