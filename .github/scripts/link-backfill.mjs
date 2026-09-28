import fs from 'node:fs';
import { parseClosingIssueNumbers } from './lib/closing-issues.mjs';

const token = process.env.GH_TOKEN;
const [owner, repo] = process.env.GITHUB_REPOSITORY.split('/');
const dryRun = process.env.DRY_RUN === 'true';
const prNumberOverride = process.env.PR_NUMBER_OVERRIDE;

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

async function backfillForPullRequest(targetPr) {
  const issueNumbers = parseClosingIssueNumbers(targetPr.body);
  if (!issueNumbers.length) {
    console.log(`PR #${targetPr.number} não referencia nenhuma issue via Closes/Fixes/Resolves.`);
    return;
  }

  for (const number of issueNumbers) {
    try {
      const issue = await api(`/repos/${owner}/${repo}/issues/${number}`).catch(() => null);
      if (!issue || issue.pull_request) {
        console.log(`#${number} não é uma issue válida neste repositório, ignorando.`);
        continue;
      }

      const linked = await graphql(
        `
          query ($owner: String!, $repo: String!, $number: Int!) {
            repository(owner: $owner, name: $repo) {
              issue(number: $number) {
                id
                closedByPullRequestsReferences(first: 50, includeClosedPrs: true) {
                  nodes { number }
                }
              }
            }
          }
        `,
        { owner, repo, number },
      );
      const issueNode = linked.repository.issue;
      const alreadyLinked = issueNode.closedByPullRequestsReferences.nodes.some(
        (node) => node.number === targetPr.number,
      );
      if (alreadyLinked) {
        console.log(`#${number} já está vinculada à PR #${targetPr.number}, nada a fazer.`);
        continue;
      }

      if (dryRun) {
        console.log(`[dry-run] linkaria a issue #${number} <- PR #${targetPr.number}`);
        continue;
      }

      await graphql(
        `
          mutation ($issueId: ID!, $prIds: [ID!]!) {
            addCloseIssueReferences(input: { issueId: $issueId, pullRequestIds: $prIds }) {
              issue { id }
            }
          }
        `,
        { issueId: issueNode.id, prIds: [targetPr.node_id] },
      );
      console.log(`Vinculada a issue #${number} <- PR #${targetPr.number}.`);
    } catch (error) {
      console.error(`::warning::link-backfill falhou para #${number}: ${error.message}`);
      // Never abort the run because of one problematic issue reference — this
      // script is bookkeeping, not a merge gate.
    }
  }
}

if (prNumberOverride) {
  // workflow_dispatch smoke-test path: run against an already-open PR by number.
  const targetPr = await api(`/repos/${owner}/${repo}/pulls/${prNumberOverride}`);
  await backfillForPullRequest(targetPr);
} else {
  const event = JSON.parse(fs.readFileSync(process.env.GITHUB_EVENT_PATH, 'utf8'));
  if (event.pull_request) await backfillForPullRequest(event.pull_request);
}
