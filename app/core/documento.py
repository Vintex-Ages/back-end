"""Documento do vendedor (RN-30) — CPF e CNPJ, num lugar só (back-end#217).

Porte de `front-end/src/utils/document.ts`, de propósito na mesma forma: as
duas pontas recusam os mesmos documentos, e mudar a regra é mudar nas duas.
A validação confere o dígito verificador, não só o tamanho — `111.111.111-11`
tem 11 dígitos e passa no cálculo, por isso sequências repetidas são recusadas
à parte.

O front valida para o erro aparecer no campo antes do envio; esta é a
validação que vale, porque a API pode ser chamada direto.
"""

import re
from typing import Literal

DocumentType = Literal["CPF", "CNPJ"]

DOCUMENT_DIGITS: dict[str, int] = {"CPF": 11, "CNPJ": 14}

_CPF_WEIGHTS = ([10, 9, 8, 7, 6, 5, 4, 3, 2], [11, 10, 9, 8, 7, 6, 5, 4, 3, 2])
_CNPJ_WEIGHTS = (
    [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2],
    [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2],
)


def only_digits(value: str) -> str:
    """Só 0-9, como o `/\\D/g` do front. `str.isdigit` aceitaria dígito de outros
    alfabetos ("٣", "²"), que não é documento."""
    return re.sub(r"[^0-9]", "", value)


def _is_repeated_sequence(digits: str) -> bool:
    """Todos os dígitos iguais passam no cálculo, mas não são documento real."""
    return len(set(digits)) == 1


def _check_digit(digits: str, weights: list[int]) -> int:
    """Módulo 11: soma dos dígitos vezes os pesos; resto menor que 2 vira 0,
    senão `11 - resto`. É a mesma conta para CPF e CNPJ, só mudam os pesos."""
    rest = sum(int(digit) * weight for digit, weight in zip(digits, weights)) % 11
    return 0 if rest < 2 else 11 - rest


def _is_valid(value: str, length: int, weights: tuple[list[int], list[int]]) -> bool:
    digits = only_digits(value)
    if len(digits) != length or _is_repeated_sequence(digits):
        return False
    first, second = weights
    return _check_digit(digits, first) == int(digits[-2]) and _check_digit(
        digits, second
    ) == int(digits[-1])


def is_valid_cpf(value: str) -> bool:
    return _is_valid(value, DOCUMENT_DIGITS["CPF"], _CPF_WEIGHTS)


def is_valid_cnpj(value: str) -> bool:
    return _is_valid(value, DOCUMENT_DIGITS["CNPJ"], _CNPJ_WEIGHTS)


def is_valid_document(document_type: str, value: str) -> bool:
    if document_type == "CPF":
        return is_valid_cpf(value)
    if document_type == "CNPJ":
        return is_valid_cnpj(value)
    return False
