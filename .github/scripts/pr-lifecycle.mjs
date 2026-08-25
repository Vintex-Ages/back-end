import fs from "node:fs";

const event = JSON.parse(
  fs.readFileSync(process.env.GITHUB_EVENT_PATH, "utf8"),
);
const pr = event.pull_request;
const token = process.env.GH_TOKEN;
const [owner, repo] = process.env.GITHUB_REPOSITORY.split("/");
const org = process.env.PROJECT_ORG;
const sourceNumber = Number(process.env.SOURCE_PROJECT_NUMBER);
const aggregateNumber = Number(process.env.AGGREGATE_PROJECT_NUMBER);

if (!token || !pr) process.exit(0);

const issueNumbers = [
  ...(pr.body || "").matchAll(/\b(?:Closes|Fixes|Resolves)\s+#(\d+)/gi),
].map((match) => Number(match[1]));
if (!issueNumbers.length) process.exit(0);

let status = pr.draft ? "In progress" : "In review";
if (event.action === "closed" && !pr.merged) status = "In progress";
if (event.action === "closed" && pr.merged && pr.base.ref === "develop")
  status = "Done";

const api = async (path, options = {}) => {
  const response = await fetch(`https://api.github.com${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      ...(options.headers || {}),
    },
  });
  if (!response.ok)
    throw new Error(
      `${options.method || "GET"} ${path}: ${response.status} ${await response.text()}`,
    );
  return response.status === 204 ? null : response.json();
};

const graphql = async (query, variables) => {
  const data = await api("/graphql", {
    method: "POST",
    body: JSON.stringify({ query, variables }),
    headers: { "Content-Type": "application/json" },
  });
  if (data.errors) throw new Error(JSON.stringify(data.errors));
  return data.data;
};

async function setStatus(projectNumber, contentId, desiredStatus) {
  const data = await graphql(
    `
      query ($org: String!, $number: Int!) {
        organization(login: $org) {
          projectV2(number: $number) {
            id
            fields(first: 50) {
              nodes {
                ... on ProjectV2SingleSelectField {
                  id
                  name
                  options {
                    id
                    name
                  }
                }
              }
            }
            items(first: 100) {
              nodes {
                id
                content {
                  ... on Issue {
                    id
                  }
                  ... on PullRequest {
                    id
                  }
                }
              }
            }
          }
        }
      }
    `,
    { org, number: projectNumber },
  );
  const project = data.organization.projectV2;
  const field = project.fields.nodes.find((item) => item.name === "Status");
  const option = field?.options.find(
    (item) => item.name.toLowerCase() === desiredStatus.toLowerCase(),
  );
  if (!field || !option)
    throw new Error(
      `Status ${desiredStatus} ausente no Project ${projectNumber}`,
    );
  let item = project.items.nodes.find(
    (candidate) => candidate.content?.id === contentId,
  );
  if (!item) {
    const added = await graphql(
      `
        mutation ($project: ID!, $content: ID!) {
          addProjectV2ItemById(
            input: { projectId: $project, contentId: $content }
          ) {
            item {
              id
            }
          }
        }
      `,
      { project: project.id, content: contentId },
    );
    item = added.addProjectV2ItemById.item;
  }
  await graphql(
    `
      mutation ($project: ID!, $item: ID!, $field: ID!, $option: String!) {
        updateProjectV2ItemFieldValue(
          input: {
            projectId: $project
            itemId: $item
            fieldId: $field
            value: { singleSelectOptionId: $option }
          }
        ) {
          projectV2Item {
            id
          }
        }
      }
    `,
    { project: project.id, item: item.id, field: field.id, option: option.id },
  );
}

for (const number of issueNumbers) {
  const issue = await api(`/repos/${owner}/${repo}/issues/${number}`);
  if (status === "Done" && issue.state !== "closed") {
    await api(`/repos/${owner}/${repo}/issues/${number}`, {
      method: "PATCH",
      body: JSON.stringify({ state: "closed", state_reason: "completed" }),
      headers: { "Content-Type": "application/json" },
    });
    await api(`/repos/${owner}/${repo}/issues/${number}/comments`, {
      method: "POST",
      body: JSON.stringify({
        body: `Concluída pelo merge de #${pr.number} em develop.`,
      }),
      headers: { "Content-Type": "application/json" },
    });
  }
  await setStatus(sourceNumber, issue.node_id, status);
  await setStatus(aggregateNumber, issue.node_id, status);
}
