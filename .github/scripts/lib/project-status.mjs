/**
 * Same "Status" single-select read/write shape as pr-lifecycle.mjs's inline
 * setStatus() (query fields + items, find the option, add the item if
 * missing, then mutate). Extracted here — without touching pr-lifecycle.mjs —
 * so close-guard.mjs can snapshot the Status before reopening an issue and
 * restore it afterward, as a defense against the native Project workflow
 * rules ("Item closed" / "Auto-close issue") still reacting to the same event.
 */
export function createProjectStatusClient({ token, org }) {
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

  const projectCache = new Map();

  async function loadProject(projectNumber) {
    if (projectCache.has(projectNumber)) return projectCache.get(projectNumber);
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
                    options { id name }
                  }
                }
              }
              items(first: 100) {
                nodes {
                  id
                  content {
                    ... on Issue { id }
                    ... on PullRequest { id }
                  }
                  fieldValues(first: 50) {
                    nodes {
                      ... on ProjectV2ItemFieldSingleSelectValue {
                        name
                        field { ... on ProjectV2SingleSelectField { id name } }
                      }
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
    const statusField = project.fields.nodes.find((field) => field?.name === 'Status');
    if (!statusField) throw new Error(`Campo Status ausente no Project ${projectNumber}`);
    const loaded = { id: project.id, statusField, items: project.items.nodes };
    projectCache.set(projectNumber, loaded);
    return loaded;
  }

  async function readStatus(projectNumber, contentId) {
    const project = await loadProject(projectNumber);
    const item = project.items.find((candidate) => candidate.content?.id === contentId);
    const value = item?.fieldValues.nodes.find(
      (fieldValue) => fieldValue.field?.id === project.statusField.id,
    );
    return value?.name ?? null;
  }

  async function setStatus(projectNumber, contentId, desiredStatus) {
    const project = await loadProject(projectNumber);
    const option = project.statusField.options.find(
      (candidate) => candidate.name.toLowerCase() === desiredStatus.toLowerCase(),
    );
    if (!option) throw new Error(`Status ${desiredStatus} ausente no Project ${projectNumber}`);

    let item = project.items.find((candidate) => candidate.content?.id === contentId);
    if (!item) {
      const added = await graphql(
        `
          mutation ($project: ID!, $content: ID!) {
            addProjectV2ItemById(input: { projectId: $project, contentId: $content }) {
              item { id }
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
            projectV2Item { id }
          }
        }
      `,
      { project: project.id, item: item.id, field: project.statusField.id, option: option.id },
    );

    // Invalidate the cache entry: the item we just touched (added or updated)
    // must be visible to a subsequent readStatus() in the same run.
    projectCache.delete(projectNumber);
  }

  return { readStatus, setStatus };
}
