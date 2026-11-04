"""Duração do vídeo lida do cabeçalho e a recusa no upload (back-end#270, o
critério da #219).

Os vídeos são montados aqui, caixa por caixa, com só o que o leitor olha: a
`ftyp`, a `moov` com a `mvhd` e uma `mdat` de enchimento. Um arquivo de verdade
tem muito mais caixas, que o leitor pula pelo tamanho.
"""

from __future__ import annotations

import struct

import pytest

from app.controllers.media_controller import ArquivoRecebido, MediaController
from app.core.errors import ValidationError
from app.services.media_storage import MediaStorage
from app.services.video_duration import DuracaoIlegivel, duracao_em_segundos


def caixa(tipo: bytes, corpo: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(corpo), tipo) + corpo


def mvhd(segundos: float, *, timescale: int = 600, versao: int = 0) -> bytes:
    duracao = round(segundos * timescale)
    if versao == 0:
        corpo = bytes([0, 0, 0, 0]) + struct.pack(">IIII", 0, 0, timescale, duracao)
    else:
        corpo = bytes([1, 0, 0, 0]) + struct.pack(">QQIQ", 0, 0, timescale, duracao)
    # Taxa, volume, matriz e o resto: o leitor não olha.
    return caixa(b"mvhd", corpo + b"\x00" * 80)


def video(
    segundos: float, *, versao: int = 0, moov_no_fim: bool = False, marca=b"isom"
) -> bytes:
    ftyp = caixa(b"ftyp", marca + b"\x00\x00\x02\x00" + marca)
    moov = caixa(b"moov", mvhd(segundos, versao=versao))
    mdat = caixa(b"mdat", b"\x00" * 64)
    return ftyp + (mdat + moov if moov_no_fim else moov + mdat)


# --- leitor ----------------------------------------------------------------------


@pytest.mark.parametrize("versao", [0, 1])
def test_le_a_duracao_nas_duas_versoes_da_mvhd(versao):
    assert duracao_em_segundos(video(4.5, versao=versao)) == pytest.approx(4.5)


def test_le_a_duracao_com_a_moov_depois_dos_dados():
    """Câmera grava a `moov` no fim; o leitor percorre o nível de cima inteiro."""
    assert duracao_em_segundos(video(3.2, moov_no_fim=True)) == pytest.approx(3.2)


def test_le_o_quicktime_do_iphone():
    assert duracao_em_segundos(video(4.0, marca=b"qt  ")) == pytest.approx(4.0)


def test_pula_caixa_com_tamanho_estendido():
    """Tamanho 1: o tamanho real vem nos 8 bytes seguintes, como numa `mdat`
    grande."""
    corpo = b"\x00" * 16
    mdat_grande = struct.pack(">I4sQ", 1, b"mdat", 16 + len(corpo)) + corpo
    dados = mdat_grande + caixa(b"moov", mvhd(5.0))

    assert duracao_em_segundos(dados) == pytest.approx(5.0)


def test_caixa_com_tamanho_zero_vai_ate_o_fim():
    dados = caixa(b"moov", mvhd(3.0))
    dados = struct.pack(">I", 0) + dados[4:]

    assert duracao_em_segundos(dados) == pytest.approx(3.0)


@pytest.mark.parametrize(
    "dados",
    [
        b"",
        b"isto nao e um video",
        b"\xff\xd8\xff\xe0" + b"0" * 64,  # JPEG
        caixa(b"ftyp", b"isom") + caixa(b"mdat", b"\x00" * 8),  # sem moov
        caixa(b"moov", caixa(b"trak", b"")),  # moov sem mvhd
        video(4.0)[:40],  # cortado no meio da mvhd
    ],
)
def test_arquivo_sem_duracao_legivel_levanta_erro_proprio(dados):
    with pytest.raises(DuracaoIlegivel):
        duracao_em_segundos(dados)


def test_mvhd_sem_escala_de_tempo_levanta_erro_proprio():
    corpo = bytes([0, 0, 0, 0]) + struct.pack(">IIII", 0, 0, 0, 100)
    with pytest.raises(DuracaoIlegivel):
        duracao_em_segundos(caixa(b"moov", caixa(b"mvhd", corpo)))


# --- upload ----------------------------------------------------------------------


class _S3EmMemoria:
    def __init__(self) -> None:
        self.objetos: dict[str, bytes] = {}

    def put_object(
        self, Bucket: str, Key: str, Body: bytes, ContentType: str
    ):  # noqa: N803
        self.objetos[Key] = Body


@pytest.fixture
def s3() -> _S3EmMemoria:
    return _S3EmMemoria()


@pytest.fixture
def controller(s3) -> MediaController:
    return MediaController(MediaStorage("bucket-de-teste", s3), "http://api.test")


def enviar(controller: MediaController, dados: bytes, nome: str = "clip.mp4"):
    return controller.upload("video", [ArquivoRecebido(nome, "video/mp4", dados)])


@pytest.mark.parametrize("segundos", [3.0, 4.0, 5.0, 5.04, 2.96])
def test_video_de_3_a_5_segundos_sobe_com_url_publica(controller, s3, segundos):
    """5,04 e 2,96 contam como 5,0 e 3,0: compara-se com uma casa."""
    resposta = enviar(controller, video(segundos))

    assert len(s3.objetos) == 1
    item = resposta.items[0]
    assert item.url == f"http://api.test/api/media/{item.key}"
    assert item.key.startswith("products/videos/")


@pytest.mark.parametrize(("segundos", "texto"), [(6.0, "6,0s"), (2.5, "2,5s")])
def test_video_fora_de_3_a_5_segundos_e_recusado_dizendo_a_duracao(
    controller, s3, segundos, texto
):
    with pytest.raises(ValidationError) as erro:
        enviar(controller, video(segundos))

    mensagem = str(erro.value.message)
    assert texto in mensagem
    assert "clip.mp4" in mensagem
    assert "de 3 a 5 segundos" in mensagem
    assert s3.objetos == {}


def test_video_sem_duracao_legivel_e_recusado(controller, s3):
    with pytest.raises(ValidationError) as erro:
        enviar(controller, b"\x00" * 64)

    assert "duração" in str(erro.value.message)
    assert s3.objetos == {}


def test_um_video_longo_no_envio_nao_sobe_nenhum(controller, s3):
    """Valida tudo antes de subir, como as fotos: nada fica órfão no bucket."""
    with pytest.raises(ValidationError):
        controller.upload(
            "video",
            [
                ArquivoRecebido("curto.mp4", "video/mp4", video(4.0)),
                ArquivoRecebido("longo.mp4", "video/mp4", video(30.0)),
            ],
        )

    assert s3.objetos == {}


def test_foto_nao_passa_pela_checagem_de_duracao(controller, s3):
    jpeg = b"\xff\xd8\xff\xe0" + b"0" * 64

    controller.upload("photo", [ArquivoRecebido("a.jpg", "image/jpeg", jpeg)])

    assert len(s3.objetos) == 1
