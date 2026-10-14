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

const isAlreadyInProjectError = (error) => {
  try {
    const errors = JSON.parse(error.message);
    return (
      Array.isArray(errors) &&
      errors.some(
        (entry) =>
          entry?.path?.[0] === "addProjectV2ItemById" &&
          entry?.type === "UNPROCESSABLE" &&
          /content already exists in this project/i.test(entry?.message || ""),
      )
    );
  } catch {
    return false;
  }
};

const findProjectItem = async (projectId, contentId) => {
  let after = null;
  while (true) {
    const data = await graphql(
      `
        query ($project: ID!, $after: String) {
          node(id: $project) {
            ... on ProjectV2 {
              items(first: 100, after: $after) {
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
                pageInfo {
                  hasNextPage
                  endCursor
                }
              }
            }
          }
        }
      `,
      { project: projectId, after },
    );
    const items = data.node?.items;
    const item = items?.nodes?.find((candidate) => candidate.content?.id === contentId);
    if (item) return item;
    if (!items?.pageInfo?.hasNextPage) return null;
    after = items.pageInfo.endCursor;
  }
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
    try {
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
    } catch (error) {
      if (!isAlreadyInProjectError(error)) throw error;
      item = await findProjectItem(project.id, contentId);
      if (!item) throw error;
    }
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
