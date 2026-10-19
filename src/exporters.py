"""
Exportação dos resultados em CSV, XLSX, TXT e JSON.

Responsabilidade:
    - Gerar conteúdo serializável para download no Streamlit.
    - Garantir que CSV use separador ``;`` e UTF-8 com BOM, compatível com
      planilhas brasileiras.
    - Gerar XLSX com OpenPyXL.
    - Gerar resumo textual (TXT) e estatísticas (JSON).

Observações:
    - As funções recebem o DataFrame final e retornam ``bytes`` ou ``str``.
      Não gravam em disco diretamente; o download é feito pelo Streamlit.
    - Quando vazio, o DataFrame gera arquivos válidos (cabeçalho vazio).
"""

from __future__ import annotations

import io
import json
from datetime import date, datetime
from typing import Any

import pandas as pd

from src.logger import configurar_logger

logger = configurar_logger("receita_explorer.exporters")


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _serializar_valor(valor: Any) -> Any:
    """Converte valores não nativos de JSON para tipos serializáveis.

    Args:
        valor: Valor a converter.

    Returns:
        Valor compatível com ``json.dumps``.
    """
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    return valor


def _normalizar_para_export(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza o DataFrame para exportação, tratando tipos pandas.

    Args:
        df: DataFrame de entrada.

    Returns:
        Cópia do DataFrame com colunas compatíveis com planilhas.
    """
    df_copia = df.copy()
    # Datas convertidas para string legível; objetos ``date`` não são
    # serializáveis diretamente por algumas bibliotecas.
    for coluna in df_copia.columns:
        if df_copia[coluna].dtype == object:
            df_copia[coluna] = df_copia[coluna].map(_serializar_valor)
    return df_copia


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------

def exportar_csv(df: pd.DataFrame) -> bytes:
    """Gera CSV com separador ``;`` e UTF-8 com BOM.

    Args:
        df: DataFrame a exportar.

    Returns:
        Conteúdo do arquivo em ``bytes``.

    Observações:
        - O BOM (``\\ufeff``) ajuda o Excel em pt-BR a reconhecer UTF-8.
        - CSV usa ``;`` como separador para compatibilidade com o padrão
          brasileiro.
    """
    df_norm = _normalizar_para_export(df)
    buffer = io.StringIO()
    df_norm.to_csv(buffer, sep=";", index=False, encoding="utf-8")
    return buffer.getvalue().encode("utf-8-sig")


# ---------------------------------------------------------------------------
# XLSX
# ---------------------------------------------------------------------------

def exportar_xlsx(df: pd.DataFrame) -> bytes:
    """Gera arquivo XLSX com OpenPyXL.

    Args:
        df: DataFrame a exportar.

    Returns:
        Conteúdo binário do arquivo XLSX.

    Raises:
        ImportError: Se ``openpyxl`` não estiver instalado.
    """
    df_norm = _normalizar_para_export(df)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_norm.to_excel(writer, index=False, sheet_name="resultados")
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# TXT
# ---------------------------------------------------------------------------

def exportar_txt(
    df: pd.DataFrame,
    competencia: str,
    limite_linhas: int = 5000,
) -> str:
    """Gera um resumo textual dos resultados.

    Args:
        df: DataFrame a exportar.
        competencia: Competência dos dados.
        limite_linhas: Número máximo de linhas detalhadas no TXT.

    Returns:
        Conteúdo textual.
    """
    linhas: list[str] = []
    linhas.append("=" * 78)
    linhas.append("Receita Explorer — Resumo de resultados")
    linhas.append("=" * 78)
    linhas.append(f"Competência: {competencia}")
    linhas.append(f"Gerado em: {datetime.now().isoformat(timespec='seconds')}")
    linhas.append(f"Total de registros: {len(df)}")
    linhas.append("")

    if df.empty:
        linhas.append("Nenhum registro a exibir.")
        return "\n".join(linhas)

    # Estatísticas simples
    if "UF" in df.columns:
        linhas.append("Por UF:")
        for uf, qtd in df["UF"].value_counts().items():
            linhas.append(f"  {uf}: {qtd}")
        linhas.append("")

    if "CATEGORIA_CLASSIFICADA" in df.columns:
        linhas.append("Por categoria:")
        for cat, qtd in df["CATEGORIA_CLASSIFICADA"].value_counts().items():
            linhas.append(f"  {cat}: {qtd}")
        linhas.append("")

    linhas.append("-" * 78)
    linhas.append(f"Detalhamento (até {limite_linhas} linhas):")
    linhas.append("-" * 78)

    colunas = [
        c for c in (
            "CNPJ_FORMATADO", "NOME_FANTASIA", "UF", "MUNICIPIO",
            "TELEFONE_FORMATADO", "EMAIL",
        ) if c in df.columns
    ]
    for _, row in df.head(limite_linhas).iterrows():
        partes = []
        for c in colunas:
            valor = row.get(c)
            if pd.isna(valor) if not isinstance(valor, (list, dict)) else False:
                valor = ""
            partes.append(f"{c}={valor}")
        linhas.append(" | ".join(partes))

    if len(df) > limite_linhas:
        linhas.append("")
        linhas.append(f"... e mais {len(df) - limite_linhas} linhas omitidas.")

    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# JSON de estatísticas
# ---------------------------------------------------------------------------

def exportar_json_estatisticas(estatisticas: dict[str, Any]) -> str:
    """Serializa o dicionário de estatísticas em JSON UTF-8.

    Args:
        estatisticas: Dicionário com métricas.

    Returns:
        Texto JSON formatado.
    """
    return json.dumps(estatisticas, ensure_ascii=False, indent=2, default=_serializar_valor)


__all__ = [
    "exportar_csv",
    "exportar_json_estatisticas",
    "exportar_txt",
    "exportar_xlsx",
]