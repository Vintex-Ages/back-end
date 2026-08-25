import fs from "node:fs";

const event = JSON.parse(
  fs.readFileSync(process.env.GITHUB_EVENT_PATH, "utf8"),
);
const pr = event.pull_request;
const errors = [];
const base = pr.base.ref;
const head = pr.head.ref;
const body = pr.body || "";
const repo = process.env.GITHUB_REPOSITORY;
const token = process.env.GITHUB_TOKEN;

const ordinary = base === "develop";
const promotion =
  (base === "main" && head === "develop") ||
  (base === "deploy" && head === "main");

if (!ordinary && !promotion) {
  errors.push(
    `Fluxo inválido: ${head} não pode promover diretamente para ${base}.`,
  );
}

if (ordinary) {
  const branchPattern =
    /^(feature|bugfix|hotfix|refactor|docs|chore)\/[0-9]+-[a-z0-9]+(?:-[a-z0-9]+)*$/;
  if (!branchPattern.test(head)) errors.push(`Branch inválida: ${head}.`);

  const issueMatch = body.match(/\b(?:Closes|Fixes|Resolves)\s+#(\d+)/i);
  if (!issueMatch) {
    errors.push("Inclua Closes #<issue> no corpo do PR.");
  } else if (token) {
    const [owner, name] = repo.split("/");
    const response = await fetch(
      `https://api.github.com/repos/${owner}/${name}/issues/${issueMatch[1]}`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: "application/vnd.github+json",
        },
      },
    );
    if (!response.ok)
      errors.push(`A issue #${issueMatch[1]} não existe neste repositório.`);
  }

  const types = ["Feature", "Bugfix", "Hotfix", "Refactor", "Docs", "Chore"];
  const selected = types.filter((type) =>
    new RegExp(`- \\[x\\] ${type}\\b`, "i").test(body),
  );
  if (selected.length !== 1)
    errors.push("Selecione exatamente um Tipo de mudança.");

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
  if (!section("O que foi feito"))
    errors.push("Preencha a seção O que foi feito.");
  if (!section("(Onde foi utilizado IA\\?|Uso de IA)"))
    errors.push("Declare o uso de IA ou informe que não houve uso.");
}

if (errors.length) {
  for (const error of errors) console.error(`::error::${error}`);
  process.exit(1);
}

console.log(`PR válido: ${head} -> ${base}`);
