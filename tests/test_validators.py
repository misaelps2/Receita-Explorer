"""Testes do módulo :mod:`src.validators`."""

from __future__ import annotations

from datetime import date

import pytest

from src.validators import (
    _calcular_dv_cnpj,
    converter_data_rfb,
    formatar_cep,
    formatar_cnpj,
    formatar_data_br,
    formatar_telefone,
    limpar_texto,
    montar_cnpj,
    normalizar_cep,
    normalizar_email,
    normalizar_endereco,
    normalizar_telefone,
    somente_digitos,
    validar_cnpj,
    validar_email,
)


def _cnpj_valido(base12: str) -> str:
    """Gera um CNPJ válido a partir de 12 dígitos."""
    dv1 = _calcular_dv_cnpj(base12)
    dv2 = _calcular_dv_cnpj(base12 + dv1)
    return base12 + dv1 + dv2


def test_montar_cnpj_preserva_zeros() -> None:
    """O CNPJ deve preservar zeros à esquerda."""
    cnpj = montar_cnpj("00000001", "0001", "00")
    assert cnpj is not None
    assert cnpj == "00000001000100"


def test_montar_cnpj_invalido_retorna_none() -> None:
    """Componentes ausentes ou incompletos retornam ``None``."""
    assert montar_cnpj("", "0001", "00") is None
    assert montar_cnpj("123", "0001", "00") is None


def test_validar_cnpj_ok() -> None:
    """CNPJ com DVs corretos deve ser válido."""
    cnpj = _cnpj_valido("112223330001")
    assert validar_cnpj(cnpj) is True


def test_validar_cnpj_dv_errado() -> None:
    """CNPJ com DV trocado deve ser inválido."""
    cnpj = _cnpj_valido("112223330001")
    invalido = cnpj[:-1] + ("0" if cnpj[-1] != "0" else "1")
    assert validar_cnpj(invalido) is False


def test_validar_cnpj_repetidos() -> None:
    """CNPJ com todos os dígitos iguais deve ser inválido."""
    assert validar_cnpj("00000000000000") is False
    assert validar_cnpj("11111111111111") is False


def test_formatar_cnpj() -> None:
    """Formatação deve aplicar a máscara correta."""
    assert formatar_cnpj("12345678000195") == "12.345.678/0001-95"
    assert formatar_cnpj("123") is None


def test_somente_digitos() -> None:
    """Deve remover tudo que não for dígito."""
    assert somente_digitos("12.345.678/0001-95") == "12345678000195"
    assert somente_digitos(None) == ""


def test_limpar_texto_nan_e_variantes() -> None:
    """Valores textuais ausentes devem virar ``None``."""
    assert limpar_texto("  ") is None
    assert limpar_texto("nan") is None
    assert limpar_texto("NULL") is None
    assert limpar_texto(float("nan")) is None
    assert limpar_texto(" ok ") == "ok"


def test_normalizar_telefone_ok() -> None:
    """DDD + número válidos geram telefone normalizado."""
    assert normalizar_telefone("62", "99999-9999") == "62999999999"
    assert normalizar_telefone("62", "3333-4444") == "6233334444"


def test_normalizar_telefone_incompleto() -> None:
    """Número com quantidade errada de dígitos retorna ``None``."""
    assert normalizar_telefone("62", "1234") is None
    assert normalizar_telefone("", "999999999") is None


def test_formatar_telefone() -> None:
    """Telefone deve ser formatado para fixo ou celular."""
    assert formatar_telefone("6233334444") == "(62) 3333-4444"
    assert formatar_telefone("62999999999") == "(62) 99999-9999"
    assert formatar_telefone("123") is None


def test_normalizar_email() -> None:
    """E-mail deve ser normalizado (trim + minúsculas)."""
    assert normalizar_email("  Foo@Bar.COM ") == "foo@bar.com"
    assert normalizar_email("") is None


def test_validar_email() -> None:
    """Validação sintática de e-mail."""
    assert validar_email("foo@bar.com") is True
    assert validar_email("foo@bar") is False
    assert validar_email("") is False
    assert validar_email(None) is False


def test_cep() -> None:
    """CEP deve preservar zeros e ser formatado corretamente."""
    assert normalizar_cep("74000-000") == "74000000"
    assert normalizar_cep("01234-567") == "01234567"
    assert normalizar_cep("123") is None
    assert formatar_cep("74000000") == "74000-000"


def test_normalizar_endereco_colapsa_espacos() -> None:
    """Espaços múltiplos devem ser colapsados."""
    assert normalizar_endereco("  Rua   das   Flores  ") == "Rua das Flores"
    assert normalizar_endereco("") is None


def test_converter_data_rfb() -> None:
    """Data ``AAAAMMDD`` deve ser convertida."""
    assert converter_data_rfb("20100101") == date(2010, 1, 1)
    assert converter_data_rfb("00000000") is None
    assert converter_data_rfb("") is None
    assert converter_data_rfb("20109999") is None


def test_formatar_data_br() -> None:
    """Data deve ser formatada para ``DD/MM/AAAA``."""
    assert formatar_data_br("20100101") == "01/01/2010"
    assert formatar_data_br(date(2015, 5, 15)) == "15/05/2015"
    assert formatar_data_br("") is None


def test_calcular_dv_cnpj_estabilidade() -> None:
    """DV calculado deve ser determinístico."""
    dv1 = _calcular_dv_cnpj("112223330001")
    dv2 = _calcular_dv_cnpj("112223330001")
    assert dv1 == dv2
    assert dv1.isdigit() and dv2.isdigit()