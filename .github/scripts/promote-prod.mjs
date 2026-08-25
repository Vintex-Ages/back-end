const token = process.env.GH_TOKEN;
const sourceRepository = process.env.GITHUB_REPOSITORY;
const sourceSha = process.env.GITHUB_SHA;
const component = process.env.COMPONENT;
const [owner, prodRepo] = process.env.PROD_REPOSITORY.split("/");
const shortSha = sourceSha.slice(0, 7);
const branch = `promote/${component}-${shortSha}`;
const path = `components/${component}/release.yml`;

const api = async (endpoint, options = {}) => {
  const response = await fetch(`https://api.github.com${endpoint}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      ...(options.headers || {}),
    },
  });
  if (!response.ok)
    throw new Error(
      `${options.method || "GET"} ${endpoint}: ${response.status} ${await response.text()}`,
    );
  return response.status === 204 ? null : response.json();
};

const base = await api(`/repos/${owner}/${prodRepo}/git/ref/heads/develop`);
try {
  await api(`/repos/${owner}/${prodRepo}/git/refs`, {
    method: "POST",
    body: JSON.stringify({ ref: `refs/heads/${branch}`, sha: base.object.sha }),
    headers: { "Content-Type": "application/json" },
  });
} catch (error) {
  if (!String(error).includes("422")) throw error;
}

let current;
try {
  current = await api(
    `/repos/${owner}/${prodRepo}/contents/${path}?ref=${encodeURIComponent(branch)}`,
  );
} catch (error) {
  if (!String(error).includes("404")) throw error;
}
const content = `schema_version: 1\ncomponent: ${component}\nsource_repository: ${sourceRepository}\nsource_branch: deploy\nsource_sha: ${sourceSha}\npromoted_at: ${new Date().toISOString()}\nsource_run_url: https://github.com/${sourceRepository}/actions/runs/${process.env.GITHUB_RUN_ID}\n`;
await api(`/repos/${owner}/${prodRepo}/contents/${path}`, {
  method: "PUT",
  body: JSON.stringify({
    message: `promote(${component}): ${shortSha}`,
    content: Buffer.from(content).toString("base64"),
    branch,
    ...(current?.sha ? { sha: current.sha } : {}),
  }),
  headers: { "Content-Type": "application/json" },
});

const pulls = await api(
  `/repos/${owner}/${prodRepo}/pulls?state=open&head=${owner}:${encodeURIComponent(branch)}`,
);
if (!pulls.length) {
  const pr = await api(`/repos/${owner}/${prodRepo}/pulls`, {
    method: "POST",
    body: JSON.stringify({
      title: `promote(${component}): ${shortSha}`,
      head: branch,
      base: "develop",
      body: `Promove ${sourceRepository}@${sourceSha}.\n\nOrigem: ${process.env.GITHUB_SERVER_URL}/${sourceRepository}/actions/runs/${process.env.GITHUB_RUN_ID}`,
    }),
    headers: { "Content-Type": "application/json" },
  });
  console.log(pr.html_url);
}
