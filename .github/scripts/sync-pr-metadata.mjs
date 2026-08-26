import fs from "node:fs";

const event = JSON.parse(
  fs.readFileSync(process.env.GITHUB_EVENT_PATH, "utf8"),
);
const config = JSON.parse(
  fs.readFileSync("config/governance/pr-automation.json", "utf8"),
);
const token = process.env.GH_TOKEN;
const [owner, repo] = process.env.GITHUB_REPOSITORY.split("/");

if (!token) throw new Error("GH_TOKEN não configurado.");

const headers = {
  Authorization: "Bearer " + token,
  Accept: "application/vnd.github+json",
  "X-GitHub-Api-Version": "2022-11-28",
};

const rest = async (path, options = {}) => {
  const response = await fetch("https://api.github.com" + path, {
    ...options,
    headers: {
      ...headers,
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    throw new Error(
      (options.method || "GET") +
        " " +
        path +
        ": " +
        response.status +
        " " +
        (await response.text()),
    );
  }
  return response.status === 204 ? null : response.json();
};

const graphql = async (query, variables) => {
  const payload = await rest("/graphql", {
    method: "POST",
    body: JSON.stringify({ query, variables }),
  });
  if (payload.errors) throw new Error(JSON.stringify(payload.errors));
  return payload.data;
};

const closingIssues = (body) => [
  ...new Set(
    [...(body || "").matchAll(/\b(?:Closes|Fixes|Resolves)\s+#(\d+)/gi)].map(
      (match) => Number(match[1]),
    ),
  ),
];

const issueIsRequired = (pr) =>
  config.issueRequiredOn.includes(pr.base.ref) &&
  !config.issueExemptHeadPatterns.some((pattern) =>
    new RegExp(pattern).test(pr.head.ref),
  );

const listPages = async (path) => {
  const separator = path.includes("?") ? "&" : "?";
  const values = [];
  for (let page = 1; ; page += 1) {
    const batch = await rest(
      path + separator + "per_page=100&page=" + page,
    );
    values.push(...batch);
    if (batch.length < 100) return values;
  }
};

const projectCache = new Map();

const fieldValueQuery = `
  fieldValues(first: 100) {
    nodes {
      ... on ProjectV2ItemFieldTextValue {
        text
        field { ... on ProjectV2Field { id name } }
      }
      ... on ProjectV2ItemFieldNumberValue {
        number
        field { ... on ProjectV2Field { id name } }
      }
      ... on ProjectV2ItemFieldDateValue {
        date
        field { ... on ProjectV2Field { id name } }
      }
      ... on ProjectV2ItemFieldSingleSelectValue {
        name
        optionId
        field { ... on ProjectV2SingleSelectField { id name } }
      }
    }
  }
`;

async function loadProject(number) {
  if (projectCache.has(number)) return projectCache.get(number);

  const headerData = await graphql(
    `
      query ($org: String!, $number: Int!) {
        organization(login: $org) {
          projectV2(number: $number) {
            id
            fields(first: 100) {
              nodes {
                ... on ProjectV2Field {
                  id
                  name
                  dataType
                }
                ... on ProjectV2SingleSelectField {
                  id
                  name
                  options { id name }
                }
              }
            }
          }
        }
      }
    `,
    { org: config.organization, number },
  );
  const project = headerData.organization.projectV2;
  if (!project) throw new Error("Project #" + number + " não encontrado.");

  const items = [];
  let cursor = null;
  do {
    const pageData = await graphql(
      `
        query ($org: String!, $number: Int!, $cursor: String) {
          organization(login: $org) {
            projectV2(number: $number) {
              items(first: 100, after: $cursor) {
                pageInfo { hasNextPage endCursor }
                nodes {
                  id
                  content {
                    ... on Issue { id url }
                    ... on PullRequest { id url }
                  }
                  ${fieldValueQuery}
                }
              }
            }
          }
        }
      `,
      { org: config.organization, number, cursor },
    );
    const connection = pageData.organization.projectV2.items;
    items.push(...connection.nodes);
    cursor = connection.pageInfo.hasNextPage
      ? connection.pageInfo.endCursor
      : null;
  } while (cursor);

  const loaded = {
    id: project.id,
    fields: project.fields.nodes.filter(Boolean),
    items,
  };
  projectCache.set(number, loaded);
  return loaded;
}

async function addProjectItem(project, contentId) {
  const data = await graphql(
    `
      mutation ($project: ID!, $content: ID!) {
        addProjectV2ItemById(
          input: { projectId: $project, contentId: $content }
        ) {
          item { id }
        }
      }
    `,
    { project: project.id, content: contentId },
  );
  const item = {
    id: data.addProjectV2ItemById.item.id,
    content: { id: contentId },
    fieldValues: { nodes: [] },
  };
  project.items.push(item);
  return item;
}

const valueForField = (item, fieldName) =>
  item?.fieldValues?.nodes.find((value) => value.field?.name === fieldName);

const sameValue = (current, desired) => {
  if (!current) return false;
  if ("singleSelectOptionId" in desired) {
    return current.optionId === desired.singleSelectOptionId;
  }
  if ("text" in desired) return current.text === desired.text;
  if ("number" in desired) return current.number === desired.number;
  if ("date" in desired) return current.date === desired.date;
  return false;
};

const desiredFieldValue = (field, source) => {
  if (typeof source === "string") {
    const option = field.options?.find(
      (candidate) => candidate.name.toLowerCase() === source.toLowerCase(),
    );
    if (!option) {
      throw new Error(
        "Opção " + source + " ausente no campo " + field.name + ".",
      );
    }
    return { singleSelectOptionId: option.id };
  }
  if (source?.name !== undefined) {
    const option = field.options?.find(
      (candidate) =>
        candidate.name.toLowerCase() === source.name.toLowerCase(),
    );
    if (!option) {
      throw new Error(
        "Opção " + source.name + " ausente no campo " + field.name + ".",
      );
    }
    return { singleSelectOptionId: option.id };
  }
  if (source?.text !== undefined) return { text: source.text };
  if (source?.number !== undefined) return { number: source.number };
  if (source?.date !== undefined) return { date: source.date };
  return null;
};

async function updateProjectField(
  project,
  item,
  field,
  source,
  current = null,
) {
  const desired = desiredFieldValue(field, source);
  if (!desired || sameValue(current, desired)) return;
  await graphql(
    `
      mutation (
        $project: ID!
        $item: ID!
        $field: ID!
        $value: ProjectV2FieldValue!
      ) {
        updateProjectV2ItemFieldValue(
          input: {
            projectId: $project
            itemId: $item
            fieldId: $field
            value: $value
          }
        ) {
          projectV2Item { id }
        }
      }
    `,
    {
      project: project.id,
      item: item.id,
      field: field.id,
      value: desired,
    },
  );
}

async function clearProjectField(project, item, field, current) {
  if (!current) return;
  await graphql(
    `
      mutation ($project: ID!, $item: ID!, $field: ID!) {
        clearProjectV2ItemFieldValue(
          input: {
            projectId: $project
            itemId: $item
            fieldId: $field
          }
        ) {
          projectV2Item { id }
        }
      }
    `,
    { project: project.id, item: item.id, field: field.id },
  );
}

async function archiveProjectItem(project, item) {
  await graphql(
    `
      mutation ($project: ID!, $item: ID!) {
        archiveProjectV2Item(
          input: { projectId: $project, itemId: $item }
        ) {
          item { id }
        }
      }
    `,
    { project: project.id, item: item.id },
  );
}

async function syncProject(number, pr, primaryIssue) {
  const project = await loadProject(number);
  let issueItem = primaryIssue
    ? project.items.find((item) => item.content?.id === primaryIssue.node_id)
    : null;
  if (primaryIssue && !issueItem) {
    issueItem = await addProjectItem(project, primaryIssue.node_id);
  }

  let prItem = project.items.find((item) => item.content?.id === pr.node_id);
  if (!prItem) prItem = await addProjectItem(project, pr.node_id);

  if (pr.state === "closed" && !pr.merged) {
    await archiveProjectItem(project, prItem);
    return;
  }

  const fields = new Map(
    project.fields.map((field) => [field.name, field]),
  );
  for (const fieldName of config.projectFields) {
    const field = fields.get(fieldName);
    if (!field) {
      throw new Error(
        "Campo " + fieldName + " ausente no Project #" + number + ".",
      );
    }
    const current = valueForField(prItem, fieldName);
    const source = issueItem
      ? valueForField(issueItem, fieldName)
      : config.promotionDefaults[fieldName];
    if (source !== undefined) {
      await updateProjectField(project, prItem, field, source, current);
    } else {
      await clearProjectField(project, prItem, field, current);
    }
  }

  const statusField = fields.get("Status");
  if (!statusField) {
    throw new Error("Campo Status ausente no Project #" + number + ".");
  }
  const statusName =
    pr.state === "closed" && pr.merged
      ? "Done"
      : pr.draft
        ? "In progress"
        : "In review";
  await updateProjectField(
    project,
    prItem,
    statusField,
    statusName,
    valueForField(prItem, "Status"),
  );
}

const changeLabel = (body) => {
  const types = ["feature", "bugfix", "hotfix", "refactor", "docs", "chore"];
  const selected = types.find((type) =>
    new RegExp("- \\[x\\] " + type + "\\b", "i").test(body || ""),
  );
  return selected ? "change:" + selected : null;
};

const equalSets = (left, right) =>
  left.size === right.size && [...left].every((value) => right.has(value));

async function syncRepositoryMetadata(pr, issues) {
  if (!issues.length) return;

  const labels = new Set();
  const assignees = new Set();
  for (const issue of issues) {
    for (const label of issue.labels || []) {
      labels.add(typeof label === "string" ? label : label.name);
    }
    for (const assignee of issue.assignees || []) {
      assignees.add(assignee.login);
    }
  }
  const derived = changeLabel(pr.body);
  if (derived) labels.add(derived);
  if (!assignees.size && pr.user.type === "User") {
    assignees.add(pr.user.login);
  }

  const currentLabels = new Set(
    (pr.labels || []).map((label) =>
      typeof label === "string" ? label : label.name,
    ),
  );
  const currentAssignees = new Set(
    (pr.assignees || []).map((assignee) => assignee.login),
  );
  const desiredMilestone = issues[0].milestone?.number ?? null;
  const currentMilestone = pr.milestone?.number ?? null;

  if (
    !equalSets(labels, currentLabels) ||
    !equalSets(assignees, currentAssignees) ||
    desiredMilestone !== currentMilestone
  ) {
    await rest(
      "/repos/" + owner + "/" + repo + "/issues/" + pr.number,
      {
        method: "PATCH",
        body: JSON.stringify({
          labels: [...labels],
          assignees: [...assignees],
          milestone: desiredMilestone,
        }),
      },
    );
  }
}

async function syncPullRequest(inputPr) {
  const pr = await rest(
    "/repos/" + owner + "/" + repo + "/pulls/" + inputPr.number,
  );
  const issueNumbers = closingIssues(pr.body);
  const required = issueIsRequired(pr);

  if (required && !issueNumbers.length) {
    throw new Error(
      "PR #" + pr.number + " precisa indicar Closes #<issue>.",
    );
  }

  const branchIssue = pr.head.ref.match(
    /^(?:feature|bugfix|hotfix|refactor|docs|chore)\/(\d+)-/,
  );
  if (
    required &&
    (!branchIssue || Number(branchIssue[1]) !== issueNumbers[0])
  ) {
    throw new Error(
      "A issue primária do PR #" +
        pr.number +
        " deve coincidir com o número da branch.",
    );
  }

  const issues = [];
  for (const number of issueNumbers) {
    const issue = await rest(
      "/repos/" + owner + "/" + repo + "/issues/" + number,
    );
    if (issue.pull_request) {
      throw new Error("#" + number + " não é uma issue.");
    }
    issues.push(issue);
  }

  const milestoneTitles = new Set(
    issues.map((issue) => issue.milestone?.title).filter(Boolean),
  );
  if (milestoneTitles.size > 1) {
    throw new Error(
      "Issues vinculadas ao PR #" +
        pr.number +
        " possuem milestones diferentes.",
    );
  }

  await syncRepositoryMetadata(pr, issues);

  const projectNumbers = [
    config.sourceProjectNumber,
    config.aggregateProjectNumber,
  ].filter((value, index, values) => value && values.indexOf(value) === index);
  for (const number of projectNumbers) {
    await syncProject(number, pr, issues[0] || null);
  }

  console.log(
    "PR #" +
      pr.number +
      " sincronizado" +
      (issueNumbers.length
        ? " com as issues " + issueNumbers.map((number) => "#" + number).join(", ")
        : " como promoção sem issue") +
      ".",
  );
}

async function selectedPullRequests() {
  if (event.pull_request) return [event.pull_request];

  const open = await listPages(
    "/repos/" + owner + "/" + repo + "/pulls?state=open",
  );
  if (event.issue && !event.issue.pull_request) {
    return open.filter((pr) =>
      closingIssues(pr.body).includes(event.issue.number),
    );
  }
  return open;
}

const failures = [];
for (const pr of await selectedPullRequests()) {
  try {
    await syncPullRequest(pr);
  } catch (error) {
    failures.push("PR #" + pr.number + ": " + error.message);
  }
}

if (failures.length) {
  for (const failure of failures) console.error("::error::" + failure);
  process.exit(1);
}
