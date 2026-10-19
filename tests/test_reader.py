"""Testes do módulo :mod:`src.reader`."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.filters import FiltroConfig
from src.reader import (
    COLUNAS_ESTABELECIMENTOS,
    processar_arquivo_em_blocos,
)


def test_processar_arquivo_sintetico(arquivo_sintetico: Path) -> None:
    """O processamento deve ler duas linhas e aprovar as duas."""
    resultado = processar_arquivo_em_blocos(
        caminho=arquivo_sintetico,
        filtros=FiltroConfig(),
        chunk_size=10,
    )
    assert resultado.registros_lidos == 2
    assert resultado.registros_aprovados == 2
    assert resultado.blocos_processados >= 1
    assert len(resultado.dataframe) == 2
    assert "CNPJ" in resultado.dataframe.columns
    assert resultado.dataframe["CNPJ"].iloc[0] == "12345678000195"


def test_processar_com_filtro_uf(arquivo_sintetico: Path) -> None:
    """Filtro por UF deve reduzir os resultados."""
    resultado = processar_arquivo_em_blocos(
        caminho=arquivo_sintetico,
        filtros=FiltroConfig(uf="SP"),
        chunk_size=10,
    )
    assert resultado.registros_lidos == 2
    assert resultado.registros_aprovados == 1
    assert resultado.dataframe.iloc[0]["UF"] == "SP"


def test_processar_arquivo_vazio(tmp_path: Path) -> None:
    """Arquivo vazio deve levantar ``ValueError``."""
    caminho = tmp_path / "vazio.csv"
    caminho.write_text("", encoding="utf-8")
    with pytest.raises(ValueError):
        processar_arquivo_em_blocos(caminho, FiltroConfig(), chunk_size=10)


def test_processar_arquivo_inexistente(tmp_path: Path) -> None:
    """Arquivo inexistente deve levantar ``FileNotFoundError``."""
    caminho = tmp_path / "nao_existe.csv"
    with pytest.raises(FileNotFoundError):
        processar_arquivo_em_blocos(caminho, FiltroConfig(), chunk_size=10)


def test_layout_30_colunas() -> None:
    """O layout oficial deve ter exatamente 30 colunas."""
    assert len(COLUNAS_ESTABELECIMENTOS) == 30
    assert COLUNAS_ESTABELECIMENTOS[0] == "CNPJ_BASICO"
    assert COLUNAS_ESTABELECIMENTOS[-1] == "DATA_SITUACAO_ESPECIAL"