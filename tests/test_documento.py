"""Dígito verificador de CPF e CNPJ (back-end#217).

Os casos são os de `front-end/src/utils/document.test.ts`: as duas pontas
precisam aceitar e recusar os mesmos documentos.
"""

import pytest

from app.core.documento import (
    is_valid_cnpj,
    is_valid_cpf,
    is_valid_document,
    only_digits,
)


def test_only_digits_remove_tudo_que_nao_e_digito():
    assert only_digits("529.982.247-25") == "52998224725"
    assert only_digits("abc") == ""


def test_only_digits_ignora_digito_de_outro_alfabeto():
    """`str.isdigit` aceitaria "²" e "٣"; documento é só 0-9, como no front."""
    assert only_digits("529²982٣") == "529982"


@pytest.mark.parametrize("cpf", ["529.982.247-25", "52998224725", "111.444.777-35"])
def test_aceita_cpf_valido(cpf):
    assert is_valid_cpf(cpf) is True


@pytest.mark.parametrize(
    "cpf",
    [
        pytest.param("529.982.247-24", id="digito verificador errado"),
        pytest.param("111.444.777-36", id="segundo digito errado"),
        pytest.param("111.111.111-11", id="digitos repetidos"),
        pytest.param("000.000.000-00", id="zeros"),
        pytest.param("529.982.247", id="incompleto"),
        pytest.param("", id="vazio"),
        pytest.param("529982247251", id="comprido demais"),
    ],
)
def test_recusa_cpf_invalido(cpf):
    assert is_valid_cpf(cpf) is False


@pytest.mark.parametrize(
    "cnpj", ["11.222.333/0001-81", "11222333000181", "60.701.190/0001-04"]
)
def test_aceita_cnpj_valido(cnpj):
    assert is_valid_cnpj(cnpj) is True


@pytest.mark.parametrize(
    "cnpj",
    [
        pytest.param("11.222.333/0001-82", id="digito verificador errado"),
        pytest.param("11.222.333/0001-91", id="primeiro digito errado"),
        pytest.param("00.000.000/0000-00", id="digitos repetidos"),
        pytest.param("11.222.333/0001", id="incompleto"),
        pytest.param("", id="vazio"),
    ],
)
def test_recusa_cnpj_invalido(cnpj):
    assert is_valid_cnpj(cnpj) is False


def test_valida_pelo_tipo_um_cpf_valido_nao_passa_como_cnpj():
    assert is_valid_document("CPF", "529.982.247-25") is True
    assert is_valid_document("CNPJ", "529.982.247-25") is False
    assert is_valid_document("CNPJ", "11.222.333/0001-81") is True
    assert is_valid_document("CPF", "11.222.333/0001-81") is False


def test_tipo_desconhecido_e_recusado():
    assert is_valid_document("RG", "52998224725") is False
