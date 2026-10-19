"""Testes do módulo :mod:`src.filters`."""

from __future__ import annotations

from datetime import date

import pandas as pd

from src.filters import (
    FiltroConfig,
    aplicar_filtros,
    classificar_dataframe,
    classificar_nome,
    remover_duplicados,
)


def test_filtro_uf(df_exemplo: pd.DataFrame) -> None:
    """Filtro por UF deve manter apenas os registros correspondentes."""
    filtrado = aplicar_filtros(df_exemplo, FiltroConfig(uf="GO"))
    assert len(filtrado) == 1
    assert filtrado.iloc[0]["UF"] == "GO"


def test_filtro_municipio(df_exemplo: pd.DataFrame) -> None:
    """Filtro por código de município."""
    filtrado = aplicar_filtros(df_exemplo, FiltroConfig(municipio_codigo="5208707"))
    assert len(filtrado) == 1


def test_filtro_situacao(df_exemplo: pd.DataFrame) -> None:
    """Filtro por situação cadastral."""
    filtrado = aplicar_filtros(df_exemplo, FiltroConfig(situacoes=["02"]))
    assert len(filtrado) == 2
    filtrado = aplicar_filtros(df_exemplo, FiltroConfig(situacoes=["08"]))
    assert len(filtrado) == 0


def test_filtro_cnae_principal(df_exemplo: pd.DataFrame) -> None:
    """Filtro por prefixo do CNAE principal."""
    filtrado = aplicar_filtros(df_exemplo, FiltroConfig(cnae_principal_prefixo="4637"))
    assert len(filtrado) == 1


def test_filtro_cnaes_interesse_inclui_secundario(df_exemplo: pd.DataFrame) -> None:
    """CNAE secundário também deve satisfazer o filtro."""
    filtrado = aplicar_filtros(df_exemplo, FiltroConfig(cnaes_interesse=["4637"]))
    assert len(filtrado) == 2


def test_filtro_palavras_chave_incluir(df_exemplo: pd.DataFrame) -> None:
    """Palavra-chave incluída deve reduzir o conjunto."""
    filtrado = aplicar_filtros(
        df_exemplo, FiltroConfig(palavras_chave_incluir=["distribuidora"])
    )
    assert len(filtrado) == 1
    assert filtrado.iloc[0]["NOME_FANTASIA"].startswith("Distribuidora")


def test_filtro_palavras_chave_excluir(df_exemplo: pd.DataFrame) -> None:
    """Palavra-chave excluída remove registros correspondentes."""
    filtrado = aplicar_filtros(
        df_exemplo, FiltroConfig(palavras_chave_excluir=["beta"])
    )
    assert len(filtrado) == 1


def test_filtro_exigir_telefone(df_exemplo: pd.DataFrame) -> None:
    """Todos os registros possuem telefone na fixture."""
    filtrado = aplicar_filtros(df_exemplo, FiltroConfig(exigir_telefone=True))
    assert len(filtrado) == 2


def test_filtro_exigir_email(df_exemplo: pd.DataFrame) -> None:
    """Todos os registros possuem e-mail válido na fixture."""
    filtrado = aplicar_filtros(df_exemplo, FiltroConfig(exigir_email=True))
    assert len(filtrado) == 2


def test_filtro_periodo(df_exemplo: pd.DataFrame) -> None:
    """Intervalo de datas deve filtrar registros corretamente."""
    filtrado = aplicar_filtros(
        df_exemplo,
        FiltroConfig(
            data_inicio_atividade_min=date(2012, 1, 1),
            data_inicio_atividade_max=date(2020, 1, 1),
        ),
    )
    assert len(filtrado) == 1
    assert filtrado.iloc[0]["NOME_FANTASIA"] == "Empório Beta"


def test_combinacao_and(df_exemplo: pd.DataFrame) -> None:
    """AND exige que todos os filtros sejam satisfeitos."""
    config = FiltroConfig(uf="GO", palavras_chave_incluir=["beta"], combinacao="AND")
    filtrado = aplicar_filtros(df_exemplo, config)
    assert len(filtrado) == 0


def test_combinacao_or(df_exemplo: pd.DataFrame) -> None:
    """OR aceita registros que satisfaçam ao menos um filtro."""
    config = FiltroConfig(uf="GO", palavras_chave_incluir=["beta"], combinacao="OR")
    filtrado = aplicar_filtros(df_exemplo, config)
    assert len(filtrado) == 2


def test_sem_filtros_retorna_tudo(df_exemplo: pd.DataFrame) -> None:
    """Sem filtros, o DataFrame original deve ser retornado."""
    filtrado = aplicar_filtros(df_exemplo, FiltroConfig())
    assert len(filtrado) == len(df_exemplo)


def test_remover_duplicados(df_exemplo: pd.DataFrame) -> None:
    """Duplicados pelo CNPJ completo devem ser removidos."""
    df_dup = pd.concat([df_exemplo, df_exemplo], ignore_index=True)
    sem_dup = remover_duplicados(df_dup)
    assert len(sem_dup) == len(df_exemplo)


def test_remover_duplicados_sem_cnpj() -> None:
    """Sem coluna ``CNPJ``, retorna o DataFrame original."""
    df = pd.DataFrame({"A": [1, 2, 3]})
    assert remover_duplicados(df).equals(df)


def test_classificar_nome() -> None:
    """Classificação por palavras-chave respeita precedência."""
    regras = {
        "Distribuidora": ["distribuidora"],
        "Empório": ["empório", "emporio"],
        "Outros": [],
    }
    assert classificar_nome("Distribuidora Alfa", regras) == "Distribuidora"
    assert classificar_nome("EMPORIO Central", regras) == "Empório"
    assert classificar_nome("Loja qualquer", regras) == "Outros"
    assert classificar_nome(None, regras) == "Outros"


def test_classificar_dataframe(df_exemplo: pd.DataFrame) -> None:
    """A coluna ``CATEGORIA_CLASSIFICADA`` deve ser adicionada."""
    regras = {
        "Distribuidora": ["distribuidora"],
        "Empório": ["empório", "emporio"],
        "Outros": [],
    }
    df_classificado = classificar_dataframe(df_exemplo, regras)
    assert "CATEGORIA_CLASSIFICADA" in df_classificado.columns
    assert df_classificado.iloc[0]["CATEGORIA_CLASSIFICADA"] == "Distribuidora"
    assert df_classificado.iloc[1]["CATEGORIA_CLASSIFICADA"] == "Empório"


def test_classificar_dataframe_vazio() -> None:
    """DataFrame vazio deve ganhar a coluna vazia."""
    df_vazio = pd.DataFrame(columns=["NOME_FANTASIA"])
    resultado = classificar_dataframe(df_vazio, {"Outros": []})
    assert "CATEGORIA_CLASSIFICADA" in resultado.columns
    assert len(resultado) == 0