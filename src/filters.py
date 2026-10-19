"""
Filtros, combinação AND/OR e classificação por palavras-chave.

Responsabilidade:
    - Definir a configuração de filtros (:class:`FiltroConfig`).
    - Aplicar filtros sobre um DataFrame de estabelecimentos enriquecido.
    - Remover duplicados usando o CNPJ completo como chave.
    - Classificar registros por categoria com base em palavras-chave do
      nome fantasia, respeitando precedência declarada.

Observações:
    - Filtros por CNAE (principal ou lista de interesse) e classificação
      por nome fantasia são conceitos **distintos**: uma empresa pode ser
      selecionada por CNAE mesmo que o nome fantasia não contenha nenhuma
      palavra-chave.
    - A combinação AND exige que **todos** os grupos informados sejam
      satisfeitos. A combinação OR exige que **pelo menos um** seja
      satisfeito.
    - Filtros vazios (``None`` ou listas vazias) não restringem.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Optional

import pandas as pd

from src.logger import configurar_logger
from src.validators import (
    montar_cnpj,
    normalizar_email,
    somente_digitos,
    validar_email,
)

logger = configurar_logger("receita_explorer.filters")


# ---------------------------------------------------------------------------
# Configuração de filtros
# ---------------------------------------------------------------------------

@dataclass
class FiltroConfig:
    """Configuração dos filtros aplicáveis a um conjunto de estabelecimentos.

    Attributes:
        uf: UF desejada (ex.: ``"GO"``) ou ``None``.
        municipio_codigo: Código do município na tabela RFB (7 dígitos).
        situacoes: Lista de códigos de situação cadastral (ex.: ``["02"]``).
        cnae_principal_prefixo: Prefixo do CNAE principal.
        cnaes_interesse: Lista de CNAEs de interesse (principal ou
            secundários). Comparação por prefixo.
        palavras_chave_incluir: Nome fantasia deve conter ao menos uma.
        palavras_chave_excluir: Se contiver qualquer uma, é descartado.
        exigir_telefone: Se ``True``, apenas registros com telefone válido.
        exigir_email: Se ``True``, apenas registros com e-mail sintaticamente
            válido.
        data_inicio_atividade_min: Data mínima de início de atividade.
        data_inicio_atividade_max: Data máxima de início de atividade.
        nome_fantasia_contem: Trecho que deve aparecer no nome fantasia.
        cnpj_completo: CNPJ específico a localizar (14 dígitos).
        combinacao: ``"AND"`` ou ``"OR"``.
    """

    uf: Optional[str] = None
    municipio_codigo: Optional[str] = None
    situacoes: Optional[list[str]] = None
    cnae_principal_prefixo: Optional[str] = None
    cnaes_interesse: Optional[list[str]] = None
    palavras_chave_incluir: Optional[list[str]] = None
    palavras_chave_excluir: Optional[list[str]] = None
    exigir_telefone: bool = False
    exigir_email: bool = False
    data_inicio_atividade_min: Optional[date] = None
    data_inicio_atividade_max: Optional[date] = None
    nome_fantasia_contem: Optional[str] = None
    cnpj_completo: Optional[str] = None
    combinacao: str = "AND"


# ---------------------------------------------------------------------------
# Normalização de entradas de filtro
# ---------------------------------------------------------------------------

def _normalizar_lista(valores: Optional[Iterable[str]]) -> list[str]:
    """Remove itens vazios e aplica ``strip``.

    Args:
        valores: Iterável de strings ou ``None``.

    Returns:
        Lista de strings não vazias.
    """
    if not valores:
        return []
    return [v.strip() for v in valores if v and v.strip()]


def _normalizar_cnpj_busca(cnpj: Optional[str]) -> Optional[str]:
    """Normaliza o CNPJ informado para busca.

    Args:
        cnpj: CNPJ em qualquer formato.

    Returns:
        CNPJ com 14 dígitos, ou ``None`` se não for possível normalizar.
    """
    if not cnpj:
        return None
    digitos = somente_digitos(cnpj)
    if len(digitos) != 14:
        return None
    return digitos


# ---------------------------------------------------------------------------
# Predicados de filtro
# ---------------------------------------------------------------------------

def _predicado_uf(df: pd.DataFrame, uf: str) -> pd.Series:
    """Filtra por UF exata."""
    if "UF" not in df.columns:
        return pd.Series(False, index=df.index)
    return df["UF"].astype(str).str.upper() == uf.upper()


def _predicado_municipio(df: pd.DataFrame, codigo: str) -> pd.Series:
    """Filtra por código de município."""
    if "MUNICIPIO" not in df.columns:
        return pd.Series(False, index=df.index)
    return df["MUNICIPIO"].astype(str).str.strip() == codigo.strip()


def _predicado_situacoes(df: pd.DataFrame, situacoes: list[str]) -> pd.Series:
    """Filtra por lista de situações cadastrais."""
    if "SITUACAO_CADASTRAL" not in df.columns:
        return pd.Series(False, index=df.index)
    return df["SITUACAO_CADASTRAL"].astype(str).str.strip().isin(situacoes)


def _predicado_cnae_principal(df: pd.DataFrame, prefixo: str) -> pd.Series:
    """Filtra por prefixo do CNAE principal."""
    if "CNAE_PRINCIPAL" not in df.columns:
        return pd.Series(False, index=df.index)
    return df["CNAE_PRINCIPAL"].astype(str).str.startswith(prefixo)


def _predicado_cnaes_interesse(df: pd.DataFrame, cnaes: list[str]) -> pd.Series:
    """Filtra registros cujo CNAE principal ou algum secundário esteja na lista.

    Args:
        df: DataFrame.
        cnaes: Lista de CNAEs (comparação por prefixo).

    Returns:
        Máscara booleana.

    Observações:
        - ``CNAE_SECUNDARIOS`` é uma string separada por vírgulas. Fazemos
          a verificação em Python para manter o comportamento previsível.
    """
    if df.empty:
        return pd.Series(False, index=df.index)

    principal = df.get("CNAE_PRINCIPAL", pd.Series("", index=df.index)).astype(str)
    secundarios = df.get("CNAE_SECUNDARIOS", pd.Series("", index=df.index)).astype(str)

    def _contem(campo: str) -> bool:
        if not campo:
            return False
        for cnae in cnaes:
            if campo.startswith(cnae):
                return True
        return False

    mascara = [
        _contem(p) or any(_contem(s.strip()) for s in sec.split(",") if s.strip())
        for p, sec in zip(principal, secundarios)
    ]
    return pd.Series(mascara, index=df.index)


def _predicado_palavras_incluir(df: pd.DataFrame, palavras: list[str]) -> pd.Series:
    """Filtra por presença de qualquer palavra-chave no nome fantasia.

    Args:
        df: DataFrame.
        palavras: Lista de palavras (case-insensitive).

    Returns:
        Máscara booleana.
    """
    if "NOME_FANTASIA" not in df.columns:
        return pd.Series(False, index=df.index)
    nomes = df["NOME_FANTASIA"].astype(str).str.lower()
    mascara = pd.Series(False, index=df.index)
    for palavra in palavras:
        mascara = mascara | nomes.str.contains(palavra.lower(), regex=False, na=False)
    return mascara


def _predicado_palavras_excluir(df: pd.DataFrame, palavras: list[str]) -> pd.Series:
    """Retorna ``True`` para registros que NÃO contêm nenhuma palavra excluída."""
    if "NOME_FANTASIA" not in df.columns:
        return pd.Series(True, index=df.index)
    nomes = df["NOME_FANTASIA"].astype(str).str.lower()
    mascara = pd.Series(False, index=df.index)
    for palavra in palavras:
        mascara = mascara | nomes.str.contains(palavra.lower(), regex=False, na=False)
    return ~mascara


def _predicado_exigir_telefone(df: pd.DataFrame) -> pd.Series:
    """Registros com telefone normalizado presente."""
    if "TELEFONE_NORMALIZADO" not in df.columns:
        return pd.Series(False, index=df.index)
    return df["TELEFONE_NORMALIZADO"].notna()


def _predicado_exigir_email(df: pd.DataFrame) -> pd.Series:
    """Registros com e-mail sintaticamente válido."""
    if "EMAIL_NORMALIZADO" not in df.columns:
        return pd.Series(False, index=df.index)
    return df["EMAIL_NORMALIZADO"].map(
        lambda v: validar_email(v) if isinstance(v, str) else False
    )


def _predicado_periodo(
    df: pd.DataFrame,
    inicio: Optional[date],
    fim: Optional[date],
) -> pd.Series:
    """Registros cuja data de abertura esteja no intervalo informado."""
    if "DATA_ABERTURA" not in df.columns:
        return pd.Series(True, index=df.index)
    datas = df["DATA_ABERTURA"]
    mascara = pd.Series(True, index=df.index)
    if inicio is not None:
        mascara &= datas.map(lambda d: d is not None and d >= inicio)
    if fim is not None:
        mascara &= datas.map(lambda d: d is not None and d <= fim)
    return mascara


def _predicado_nome_fantasia(df: pd.DataFrame, trecho: str) -> pd.Series:
    """Nome fantasia contém o trecho informado."""
    if "NOME_FANTASIA" not in df.columns:
        return pd.Series(False, index=df.index)
    return (
        df["NOME_FANTASIA"]
        .astype(str)
        .str.lower()
        .str.contains(trecho.lower(), regex=False, na=False)
    )


def _predicado_cnpj(df: pd.DataFrame, cnpj: str) -> pd.Series:
    """Registro cujo CNPJ (14 dígitos) coincide exatamente."""
    if "CNPJ" not in df.columns:
        return pd.Series(False, index=df.index)
    return df["CNPJ"].astype(str) == cnpj


# ---------------------------------------------------------------------------
# Aplicação de filtros
# ---------------------------------------------------------------------------

def aplicar_filtros(df: pd.DataFrame, config: FiltroConfig) -> pd.DataFrame:
    """Aplica todos os filtros configurados a um bloco de dados.

    Args:
        df: DataFrame enriquecido (ver :mod:`src.reader`).
        config: Configuração de filtros.

    Returns:
        DataFrame filtrado.

    Observações:
        - A combinação AND/OR é aplicada aos **grupos informados**.
        - Filtros vazios são ignorados.
        - Filtros de exclusão (palavras-chave excluídas) são sempre
          aplicados em AND, independentemente de ``combinacao``, porque
          excluir é sempre uma restrição adicional.
    """
    if df.empty:
        return df

    grupos: list[pd.Series] = []

    if config.uf:
        grupos.append(_predicado_uf(df, config.uf))
    if config.municipio_codigo:
        grupos.append(_predicado_municipio(df, config.municipio_codigo))
    if config.situacoes:
        grupos.append(_predicado_situacoes(df, config.situacoes))
    if config.cnae_principal_prefixo:
        grupos.append(_predicado_cnae_principal(df, config.cnae_principal_prefixo))
    if config.cnaes_interesse:
        grupos.append(_predicado_cnaes_interesse(df, config.cnaes_interesse))
    if config.palavras_chave_incluir:
        grupos.append(_predicado_palavras_incluir(df, config.palavras_chave_incluir))
    if config.exigir_telefone:
        grupos.append(_predicado_exigir_telefone(df))
    if config.exigir_email:
        grupos.append(_predicado_exigir_email(df))
    if config.data_inicio_atividade_min or config.data_inicio_atividade_max:
        grupos.append(
            _predicado_periodo(
                df,
                config.data_inicio_atividade_min,
                config.data_inicio_atividade_max,
            )
        )
    if config.nome_fantasia_contem:
        grupos.append(_predicado_nome_fantasia(df, config.nome_fantasia_contem))
    if config.cnpj_completo:
        cnpj_norm = _normalizar_cnpj_busca(config.cnpj_completo)
        if cnpj_norm:
            grupos.append(_predicado_cnpj(df, cnpj_norm))

    if not grupos:
        # Sem filtros: aplicamos apenas as exclusões, se houver.
        if config.palavras_chave_excluir:
            return df[_predicado_palavras_excluir(df, _normalizar_lista(config.palavras_chave_excluir))]
        return df

    combinacao = config.combinacao.upper()
    if combinacao not in ("AND", "OR"):
        combinacao = "AND"

    if combinacao == "AND":
        mascara = grupos[0]
        for g in grupos[1:]:
            mascara &= g
    else:  # OR
        mascara = grupos[0]
        for g in grupos[1:]:
            mascara |= g

    if config.palavras_chave_excluir:
        excluir = _normalizar_lista(config.palavras_chave_excluir)
        mascara &= _predicado_palavras_excluir(df, excluir)

    return df[mascara]


# ---------------------------------------------------------------------------
# Duplicados
# ---------------------------------------------------------------------------

def remover_duplicados(df: pd.DataFrame) -> pd.DataFrame:
    """Remove duplicados usando o CNPJ completo como identificador.

    Args:
        df: DataFrame com coluna ``CNPJ``.

    Returns:
        DataFrame sem duplicados (mantém a primeira ocorrência).

    Observações:
        - Se a coluna ``CNPJ`` não existir, retorna o DataFrame original.
        - Registros com ``CNPJ`` ausente são mantidos individualmente
          (não podemos afirmar que sejam duplicados).
    """
    if df.empty or "CNPJ" not in df.columns:
        return df
    # Só deduplicamos linhas com CNPJ válido (14 dígitos).
    validos = df["CNPJ"].astype(str).str.len() == 14
    sem_dup = df[~validos].copy()
    com_cnpj = df[validos].drop_duplicates(subset=["CNPJ"], keep="first")
    resultado = pd.concat([sem_dup, com_cnpj], ignore_index=False)
    # Preserva a ordem original aproximada ordenando pelo índice.
    resultado = resultado.sort_index().reset_index(drop=True)
    return resultado


# ---------------------------------------------------------------------------
# Classificação por palavras-chave
# ---------------------------------------------------------------------------

def classificar_nome(nome: Optional[str], regras: dict[str, list[str]]) -> str:
    """Classifica um nome fantasia segundo regras de precedência.

    Args:
        nome: Nome fantasia.
        regras: Dicionário ``{categoria: [palavras]}`` na ordem de
            precedência (a primeira que casar vence).

    Returns:
        Categoria escolhida; ``"Outros"`` se nenhuma regra casar.

    Observações:
        - A categoria ``"Outros"`` é usada como fallback; se ela tiver
          palavras próprias, ainda assim é a última considerada.
        - Comparação case-insensitive; usa ``in`` (substring).
    """
    if not nome:
        return "Outros"
    texto = str(nome).lower()
    for categoria, palavras in regras.items():
        if categoria == "Outros":
            continue
        for palavra in palavras:
            if palavra.lower() in texto:
                return categoria
    return "Outros"


def classificar_dataframe(
    df: pd.DataFrame,
    regras: dict[str, list[str]],
) -> pd.DataFrame:
    """Adiciona a coluna ``CATEGORIA_CLASSIFICADA`` ao DataFrame.

    Args:
        df: DataFrame com coluna ``NOME_FANTASIA``.
        regras: Dicionário de regras por categoria.

    Returns:
        Cópia do DataFrame com a nova coluna.

    Observações:
        - Retorna cópia para evitar efeitos colaterais.
    """
    if df.empty:
        if "CATEGORIA_CLASSIFICADA" not in df.columns:
            df = df.copy()
            df["CATEGORIA_CLASSIFICADA"] = pd.Series(dtype=str)
        return df

    df_copia = df.copy()
    nomes = df_copia.get("NOME_FANTASIA", pd.Series("", index=df_copia.index))
    df_copia["CATEGORIA_CLASSIFICADA"] = nomes.map(
        lambda n: classificar_nome(n, regras)
    )
    return df_copia


__all__ = [
    "FiltroConfig",
    "aplicar_filtros",
    "classificar_dataframe",
    "classificar_nome",
    "remover_duplicados",
]