import fs from "node:fs";

const event = JSON.parse(
  fs.readFileSync(process.env.GITHUB_EVENT_PATH, "utf8"),
);
const config = JSON.parse(
  fs.readFileSync("config/governance/pr-automation.json", "utf8"),
);
const codeowners = fs.readFileSync(".github/CODEOWNERS", "utf8");
const pr = event.pull_request;
const token = process.env.GITHUB_TOKEN;
const [owner, repo] = process.env.GITHUB_REPOSITORY.split("/");

if (!pr) throw new Error("Evento sem Pull Request.");

for (const reviewer of config.requestedReviewers) {
  if (!codeowners.includes(`@${reviewer}`)) {
    throw new Error(`${reviewer} está ausente de .github/CODEOWNERS.`);
  }
}

const api = async (path) => {
  const response = await fetch(`https://api.github.com${path}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
    },
  });
  if (!response.ok) {
    throw new Error(`GET ${path}: ${response.status} ${await response.text()}`);
  }
  return response.json();
};

const reviews = await api(
  `/repos/${owner}/${repo}/pulls/${pr.number}/reviews?per_page=100`,
);
reviews.sort(
  (left, right) =>
    new Date(left.submitted_at || 0) - new Date(right.submitted_at || 0) ||
    left.id - right.id,
);

const latestByReviewer = new Map();
for (const review of reviews) {
  if (
    review.user?.login &&
    ["APPROVED", "CHANGES_REQUESTED", "DISMISSED"].includes(review.state)
  ) {
    latestByReviewer.set(review.user.login.toLowerCase(), review.state);
  }
}

const author = pr.user.login.toLowerCase();
const eligible = new Set(
  config.eligibleApprovers.map((login) => login.toLowerCase()),
);
const approvals = [...latestByReviewer.entries()]
  .filter(
    ([login, state]) =>
      login !== author && eligible.has(login) && state === "APPROVED",
  )
  .map(([login]) => login);

console.log(
  `Aprovações válidas: ${approvals.length}/${config.requiredApprovals} (${approvals.join(", ") || "nenhuma"}).`,
);

if (approvals.length < config.requiredApprovals) {
  console.error(
    `::error::São necessárias ${config.requiredApprovals} aprovações vigentes de AGES III ou AGES IV.`,
  );
  process.exit(1);
}
