import fs from "node:fs";

const event = JSON.parse(
  fs.readFileSync(process.env.GITHUB_EVENT_PATH, "utf8"),
);
const pr = event.pull_request;
const errors = [];
const base = pr.base.ref;
const head = pr.head.ref;
const body = pr.body || "";
const token = process.env.GITHUB_TOKEN;
const [owner, repo] = process.env.GITHUB_REPOSITORY.split("/");

const ordinary = base === "develop";
const promotion =
  (base === "main" && head === "develop") ||
  (base === "deploy" && head === "main");

if (!ordinary && !promotion) {
  errors.push(`Fluxo inválido: ${head} não pode promover diretamente para ${base}.`);
}

const closingIssues = [
  ...new Set(
    [...body.matchAll(/\b(?:Closes|Fixes|Resolves)\s+#(\d+)/gi)].map(
      (match) => Number(match[1]),
    ),
  ),
];

const getIssue = async (number) => {
  const response = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/issues/${number}`,
    {
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
      },
    },
  );
  if (!response.ok) return null;
  return response.json();
};

if (ordinary) {
  const branchMatch = head.match(
    /^(?:feature|bugfix|hotfix|refactor|docs|chore)\/(\d+)-[a-z0-9]+(?:-[a-z0-9]+)*$/,
  );
  if (!branchMatch) errors.push(`Branch inválida: ${head}.`);

  if (!closingIssues.length) {
    errors.push("Inclua Closes #<issue> no corpo do PR.");
  } else {
    if (branchMatch && Number(branchMatch[1]) !== closingIssues[0]) {
      errors.push("A primeira issue vinculada deve coincidir com o número da branch.");
    }

    const issues = [];
    for (const number of closingIssues) {
      const issue = await getIssue(number);
      if (!issue) {
        errors.push(`A issue #${number} não existe neste repositório.`);
      } else if (issue.pull_request) {
        errors.push(`#${number} é um Pull Request, não uma issue.`);
      } else {
        issues.push(issue);
      }
    }
    const milestones = new Set(
      issues.map((issue) => issue.milestone?.number).filter(Boolean),
    );
    if (milestones.size > 1) {
      errors.push("As issues vinculadas possuem milestones diferentes.");
    }
  }

  const types = ["Feature", "Bugfix", "Hotfix", "Refactor", "Docs", "Chore"];
  const selected = types.filter((type) =>
    new RegExp(`- \\[x\\] ${type}\\b`, "i").test(body),
  );
  if (selected.length !== 1) errors.push("Selecione exatamente um Tipo de mudança.");

  const section = (title) => {
    const match = body.match(
      new RegExp(`## ${title}\\s*([\\s\\S]*?)(?=\\n## |$)`, "i"),
    );
    return (match?.[1] || "")
      .replace(/<!--[\s\S]*?-->/g, "")
      .replace(/^[-\s]+$/gm, "")
      .trim();
  };
  if (!section("Descrição")) errors.push("Preencha a seção Descrição.");
  if (!section("O que foi feito")) errors.push("Preencha a seção O que foi feito.");
  if (!section("(Onde foi utilizado IA\\?|Uso de IA)")) {
    errors.push("Declare o uso de IA ou informe que não houve uso.");
  }
}

if (errors.length) {
  for (const error of errors) console.error(`::error::${error}`);
  process.exit(1);
}

console.log(`PR válido: ${head} -> ${base}`);
