"""Testes do módulo :mod:`src.exporters`."""

from __future__ import annotations

import io
import json

import pandas as pd

from src.exporters import (
    exportar_csv,
    exportar_json_estatisticas,
    exportar_txt,
    exportar_xlsx,
)


def test_exportar_csv_separador_e_bom(df_exemplo: pd.DataFrame) -> None:
    """CSV deve ter separador ``;`` e BOM (UTF-8-SIG)."""
    conteudo = exportar_csv(df_exemplo)
    assert conteudo.startswith(b"\xef\xbb\xbf")  # BOM UTF-8
    texto = conteudo.decode("utf-8-sig")
    assert ";" in texto.splitlines()[0]
    assert "NOME_FANTASIA" in texto


def test_exportar_csv_vazio() -> None:
    """DataFrame vazio deve gerar CSV válido."""
    df_vazio = pd.DataFrame(columns=["CNPJ", "NOME_FANTASIA"])
    conteudo = exportar_csv(df_vazio)
    texto = conteudo.decode("utf-8-sig")
    assert "CNPJ" in texto and "NOME_FANTASIA" in texto


def test_exportar_xlsx(df_exemplo: pd.DataFrame) -> None:
    """XLSX deve ter a assinatura PK (zip OpenXML)."""
    conteudo = exportar_xlsx(df_exemplo)
    assert conteudo[:2] == b"PK"
    # Leitura via pandas para confirmar que é um XLSX legível.
    df_lido = pd.read_excel(io.BytesIO(conteudo))
    assert len(df_lido) == len(df_exemplo)


def test_exportar_txt(df_exemplo: pd.DataFrame) -> None:
    """TXT deve conter cabeçalho, competência e totais."""
    texto = exportar_txt(df_exemplo, competencia="2026-10", limite_linhas=10)
    assert "Receita Explorer" in texto
    assert "2026-10" in texto
    assert f"Total de registros: {len(df_exemplo)}" in texto


def test_exportar_txt_vazio() -> None:
    """TXT com DataFrame vazio deve informar ausência de registros."""
    df_vazio = pd.DataFrame(columns=["CNPJ"])
    texto = exportar_txt(df_vazio, competencia="2026-10")
    assert "Nenhum registro" in texto


def test_exportar_json_estatisticas() -> None:
    """JSON deve ser válido e conter as chaves enviadas."""
    estat = {"competencia": "2026-10", "total_registros": 10}
    texto = exportar_json_estatisticas(estat)
    dados = json.loads(texto)
    assert dados["competencia"] == "2026-10"
    assert dados["total_registros"] == 10