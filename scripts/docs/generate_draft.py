"""Gera o rascunho de documentacao (VE-25) a partir do path-map.json.

Usado pelo workflow .github/workflows/documentation-draft.yml: recebe a
lista de arquivos alterados num PR, casa cada um contra os padroes de
documentation/path-map.json e produz um Markdown listando qual pagina
revisar. Caminhos sem mapeamento sao listados, nunca escondidos ou
tratados como erro -- a automacao e informativa, nao bloqueia merge.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path


@dataclass(frozen=True)
class PathMapEntry:
    pattern: str
    page: str


def load_path_map(path_map_file: Path) -> list[PathMapEntry]:
    data = json.loads(path_map_file.read_text(encoding="utf-8"))
    return [PathMapEntry(pattern=e["pattern"], page=e["page"]) for e in data["map"]]


def match_page(changed_path: str, entries: list[PathMapEntry]) -> str | None:
    """Primeiro padrao que casar vence. None se nenhum casar."""
    normalized = changed_path.replace("\\", "/")
    for entry in entries:
        if fnmatch(normalized, entry.pattern):
            return entry.page
    return None


def group_by_page(
    changed_paths: list[str], entries: list[PathMapEntry]
) -> tuple[dict[str, list[str]], list[str]]:
    """Retorna (pagina -> arquivos mapeados a ela, arquivos sem mapeamento)."""
    mapped: dict[str, list[str]] = {}
    unmapped: list[str] = []
    for changed_path in changed_paths:
        page = match_page(changed_path, entries)
        if page is None:
            unmapped.append(changed_path)
        else:
            mapped.setdefault(page, []).append(changed_path)
    return mapped, unmapped


def render_draft(mapped: dict[str, list[str]], unmapped: list[str]) -> str:
    lines = ["# Rascunho de documentacao", ""]

    if not mapped and not unmapped:
        lines.append("Nenhum arquivo alterado neste PR.")
        return "\n".join(lines) + "\n"

    if mapped:
        lines.append("## Paginas para revisar")
        lines.append("")
        for page in sorted(mapped):
            lines.append(f"### `{page}`")
            for changed_path in sorted(mapped[page]):
                lines.append(f"- `{changed_path}`")
            lines.append("")

    if unmapped:
        lines.append("## Sem mapeamento em path-map.json")
        lines.append("")
        lines.append(
            "Informativo -- nao bloqueia o merge. "
            "Considere adicionar uma entrada em `documentation/path-map.json` "
            "se algum destes caminhos merecer uma pagina propria."
        )
        lines.append("")
        for changed_path in sorted(unmapped):
            lines.append(f"- `{changed_path}`")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--changed-files-file",
        type=Path,
        required=True,
        help="Arquivo com um caminho alterado por linha (ex.: saida de git diff --name-only).",
    )
    parser.add_argument(
        "--path-map",
        type=Path,
        default=Path(__file__).resolve().parent.parent.parent
        / "documentation"
        / "path-map.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Onde escrever o rascunho. Sem isso, imprime no stdout.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)

    changed_paths = [
        line.strip()
        for line in args.changed_files_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    entries = load_path_map(args.path_map)
    mapped, unmapped = group_by_page(changed_paths, entries)
    draft = render_draft(mapped, unmapped)

    if args.output:
        args.output.write_text(draft, encoding="utf-8")
    else:
        print(draft)

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
