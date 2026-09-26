from pathlib import Path

from scripts.docs.generate_draft import (
    PathMapEntry,
    group_by_page,
    load_path_map,
    match_page,
    render_draft,
)

ENTRIES = [
    PathMapEntry(pattern="app/core/**", page="arquitetura/fundacao-http"),
    PathMapEntry(pattern="infra/**", page="infraestrutura/teste-local"),
    PathMapEntry(pattern="Makefile", page="infraestrutura/teste-local"),
]


def test_match_page_encontra_padrao_glob():
    assert match_page("app/core/errors.py", ENTRIES) == "arquitetura/fundacao-http"


def test_match_page_normaliza_barra_invertida_do_windows():
    assert match_page("app\\core\\errors.py", ENTRIES) == "arquitetura/fundacao-http"


def test_match_page_casamento_exato():
    assert match_page("Makefile", ENTRIES) == "infraestrutura/teste-local"


def test_match_page_sem_casamento_retorna_none():
    assert match_page("app/models/user.py", ENTRIES) is None


def test_group_by_page_separa_mapeados_e_sem_mapeamento():
    mapped, unmapped = group_by_page(
        [
            "app/core/errors.py",
            "infra/vintex-infra/docker-compose.yml",
            "app/models/user.py",
        ],
        ENTRIES,
    )

    assert mapped == {
        "arquitetura/fundacao-http": ["app/core/errors.py"],
        "infraestrutura/teste-local": ["infra/vintex-infra/docker-compose.yml"],
    }
    assert unmapped == ["app/models/user.py"]


def test_render_draft_sem_nenhuma_mudanca():
    draft = render_draft({}, [])

    assert "Nenhum arquivo alterado" in draft


def test_render_draft_lista_paginas_e_nao_mapeados():
    draft = render_draft(
        {"infraestrutura/teste-local": ["Makefile"]},
        ["app/models/user.py"],
    )

    assert "`infraestrutura/teste-local`" in draft
    assert "`Makefile`" in draft
    assert "Sem mapeamento em path-map.json" in draft
    assert "`app/models/user.py`" in draft
    assert "nao bloqueia o merge" in draft


def test_load_path_map_le_o_arquivo_real_do_projeto():
    path_map_file = (
        Path(__file__).resolve().parent.parent / "documentation" / "path-map.json"
    )

    entries = load_path_map(path_map_file)

    assert len(entries) > 0
    assert all(isinstance(e, PathMapEntry) for e in entries)
