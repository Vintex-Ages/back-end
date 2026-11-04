"""Duração de um vídeo MP4 ou MOV lida do cabeçalho, sem dependência nova
(back-end#270, o critério da #219).

A #219 ficou para depois porque ler duração parecia exigir `ffprobe`, que é
dependência de infra (imagem, CI). Para os dois tipos que o upload aceita
(`video/mp4` e `video/quicktime`) não exige: os dois são o mesmo formato de
caixas (ISO BMFF, que nasceu do QuickTime), e a duração está escrita na caixa
`mvhd`, dentro da `moov`, como `duration / timescale`. Não se decodifica
nenhum quadro.

Cada caixa começa com o tamanho (4 bytes, big-endian) e o tipo (4 letras).
Tamanho 1 quer dizer que o tamanho real vem nos 8 bytes seguintes; tamanho 0,
que a caixa vai até o fim do arquivo. A `moov` pode estar antes ou depois dos
dados do vídeo (`mdat`), conforme o aplicativo que gravou: por isso se percorre
o nível de cima inteiro, e não só o começo.
"""

from __future__ import annotations

import struct
from collections.abc import Iterator


class DuracaoIlegivel(ValueError):
    """O arquivo não tem uma `mvhd` legível: não é MP4/MOV, ou está cortado."""


def _caixas(dados: bytes, inicio: int, fim: int) -> Iterator[tuple[bytes, int, int]]:
    """Tipo, início do conteúdo e fim de cada caixa entre `inicio` e `fim`."""
    pos = inicio
    while pos + 8 <= fim:
        tamanho, tipo = struct.unpack_from(">I4s", dados, pos)
        cabecalho = 8
        if tamanho == 1:
            if pos + 16 > fim:
                raise DuracaoIlegivel("Caixa cortada no tamanho estendido.")
            (tamanho,) = struct.unpack_from(">Q", dados, pos + 8)
            cabecalho = 16
        elif tamanho == 0:
            tamanho = fim - pos
        if tamanho < cabecalho or pos + tamanho > fim:
            raise DuracaoIlegivel("Caixa com tamanho fora do arquivo.")
        yield tipo, pos + cabecalho, pos + tamanho
        pos += tamanho


def duracao_em_segundos(dados: bytes) -> float:
    """Duração do vídeo em segundos, ou `DuracaoIlegivel`."""
    for tipo, inicio, fim in _caixas(dados, 0, len(dados)):
        if tipo != b"moov":
            continue
        for subtipo, sub_inicio, sub_fim in _caixas(dados, inicio, fim):
            if subtipo == b"mvhd":
                return _ler_mvhd(dados, sub_inicio, sub_fim)
    raise DuracaoIlegivel("O vídeo não tem cabeçalho de duração.")


def _ler_mvhd(dados: bytes, inicio: int, fim: int) -> float:
    """`mvhd` versão 0 tem datas e duração de 4 bytes; versão 1, de 8."""
    if inicio + 4 > fim:
        raise DuracaoIlegivel("Cabeçalho de duração cortado.")
    versao = dados[inicio]
    # Pula versão e flags (4 bytes) e as datas de criação e de modificação.
    if versao == 0:
        formato, pos = ">II", inicio + 4 + 8
    elif versao == 1:
        formato, pos = ">IQ", inicio + 4 + 16
    else:
        raise DuracaoIlegivel(f"Versão de cabeçalho desconhecida: {versao}.")
    if pos + struct.calcsize(formato) > fim:
        raise DuracaoIlegivel("Cabeçalho de duração cortado.")
    timescale, duracao = struct.unpack_from(formato, dados, pos)
    if timescale == 0:
        raise DuracaoIlegivel("Cabeçalho de duração sem escala de tempo.")
    return duracao / timescale
