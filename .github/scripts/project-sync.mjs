import fs from "node:fs";

const token = process.env.GH_TOKEN;
const org = process.env.PROJECT_ORG;
const repository = process.env.GITHUB_REPOSITORY;
const sourceNumber = Number(process.env.SOURCE_PROJECT_NUMBER);
const targetNumber = Number(process.env.AGGREGATE_PROJECT_NUMBER);
const syncedFields = new Set(
  JSON.parse(fs.readFileSync("config/project/project.json", "utf8")).fields,
);

const graphql = async (query, variables) => {
  const response = await fetch("https://api.github.com/graphql", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ query, variables }),
  });
  const payload = await response.json();
  if (!response.ok || payload.errors)
    throw new Error(JSON.stringify(payload.errors || payload));
  return payload.data;
};

const projectQuery = `query($org:String!,$number:Int!){organization(login:$org){projectV2(number:$number){id fields(first:100){nodes{... on ProjectV2Field{id name dataType} ... on ProjectV2SingleSelectField{id name options{id name}}}} items(first:100){nodes{id content{... on Issue{id url repository{nameWithOwner}} ... on PullRequest{id url repository{nameWithOwner}}} fieldValues(first:100){nodes{... on ProjectV2ItemFieldTextValue{text field{... on ProjectV2Field{id name}}} ... on ProjectV2ItemFieldNumberValue{number field{... on ProjectV2Field{id name}}} ... on ProjectV2ItemFieldDateValue{date field{... on ProjectV2Field{id name}}} ... on ProjectV2ItemFieldSingleSelectValue{name optionId field{... on ProjectV2SingleSelectField{id name}}}}}}}}}}`;

const loadProject = async (number) =>
  (await graphql(projectQuery, { org, number })).organization.projectV2;
const source = await loadProject(sourceNumber);
let target = await loadProject(targetNumber);
const targetFields = new Map(
  target.fields.nodes.map((field) => [field.name, field]),
);
const targetItems = new Map(
  target.items.nodes
    .filter((item) => item.content)
    .map((item) => [item.content.id, item]),
);

for (const sourceItem of source.items.nodes) {
  if (
    !sourceItem.content ||
    sourceItem.content.repository?.nameWithOwner !== repository
  )
    continue;
  let targetItem = targetItems.get(sourceItem.content.id);
  if (!targetItem) {
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
      { project: target.id, content: sourceItem.content.id },
    );
    targetItem = added.addProjectV2ItemById.item;
    targetItems.set(sourceItem.content.id, targetItem);
  }
  for (const value of sourceItem.fieldValues.nodes) {
    const name = value.field?.name;
    if (!name || !syncedFields.has(name)) continue;
    const targetField = targetFields.get(name);
    if (!targetField)
      throw new Error(`Campo ${name} ausente no Project ${targetNumber}`);
    let fieldValue;
    if ("name" in value && value.name !== undefined) {
      const option = targetField.options?.find(
        (candidate) =>
          candidate.name.toLowerCase() === value.name.toLowerCase(),
      );
      if (!option)
        throw new Error(
          `Opção ${value.name} ausente em ${name} no Project ${targetNumber}`,
        );
      fieldValue = { singleSelectOptionId: option.id };
    } else if ("text" in value) fieldValue = { text: value.text };
    else if ("number" in value) fieldValue = { number: value.number };
    else if ("date" in value) fieldValue = { date: value.date };
    else continue;
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
            projectV2Item {
              id
            }
          }
        }
      `,
      {
        project: target.id,
        item: targetItem.id,
        field: targetField.id,
        value: fieldValue,
      },
    );
  }
}

console.log(`Project ${sourceNumber} sincronizado com ${targetNumber}.`);
