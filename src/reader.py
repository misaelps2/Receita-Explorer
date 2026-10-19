"""
Leitura em blocos do arquivo de estabelecimentos da Receita Federal.

Responsabilidade:
    - Ler o arquivo delimitado por ``;`` em blocos configuráveis.
    - Preservar zeros à esquerda em CNPJ, CEP, telefone e códigos.
    - Aplicar filtros e normalizações básicas durante a leitura.
    - Acumular métricas reais (blocos, lidos, aprovados).
    - Devolver um :class:`ResultadoProcessamento` com o DataFrame final.

Observações:
    - Não carregamos o arquivo inteiro em memória. Cada bloco é processado
      e concatenado ao acumulador apenas com as linhas aprovadas.
    - A leitura usa ``dtype=str`` para todos os campos, evitando conversões
      automáticas que apagariam zeros à esquerda.
    - O arquivo não possui cabeçalho; fornecemos os nomes das colunas
      explicitamente com base no layout oficial.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator, Optional

import pandas as pd

from src.filters import FiltroConfig, aplicar_filtros
from src.logger import configurar_logger
from src.validators import (
    converter_data_rfb,
    formatar_cnpj,
    formatar_telefone,
    montar_cnpj,
    normalizar_cep,
    normalizar_email,
    normalizar_endereco,
    normalizar_telefone,
)

logger = configurar_logger("receita_explorer.reader")


# ---------------------------------------------------------------------------
# Layout oficial do arquivo de estabelecimentos
# ---------------------------------------------------------------------------

# Nomes de coluna na ordem oficial do arquivo ESTABELE da RFB.
# Ver ``docs/fonte-dos-dados.md`` para a origem do layout.
COLUNAS_ESTABELECIMENTOS: list[str] = [
    "CNPJ_BASICO",
    "CNPJ_ORDEM",
    "CNPJ_DV",
    "MATRIZ_FILIAL",
    "NOME_FANTASIA",
    "SITUACAO_CADASTRAL",
    "DATA_SITUACAO_CADASTRAL",
    "MOTIVO_SITUACAO",
    "NOME_CIDADE_EXTERIOR",
    "PAIS",
    "DATA_INICIO_ATIVIDADE",
    "CNAE_PRINCIPAL",
    "CNAE_SECUNDARIOS",
    "TIPO_LOGRADOURO",
    "LOGRADOURO",
    "NUMERO",
    "COMPLEMENTO",
    "BAIRRO",
    "CEP",
    "UF",
    "MUNICIPIO",
    "DDD_1",
    "TELEFONE_1",
    "DDD_2",
    "TELEFONE_2",
    "DDD_FAX",
    "FAX",
    "EMAIL",
    "SITUACAO_ESPECIAL",
    "DATA_SITUACAO_ESPECIAL",
]

CHUNK_SIZE_PADRAO: int = 200_000


# ---------------------------------------------------------------------------
# Estruturas
# ---------------------------------------------------------------------------

@dataclass
class ResultadoProcessamento:
    """Resultado acumulado do processamento em blocos.

    Attributes:
        dataframe: DataFrame com todas as linhas aprovadas e enriquecidas.
        blocos_processados: Número de blocos lidos.
        registros_lidos: Total de registros lidos do arquivo.
        registros_aprovados: Total de registros que passaram pelos filtros.
        duplicados_removidos: Preenchido pela camada chamadora.
    """

    dataframe: pd.DataFrame = field(default_factory=pd.DataFrame)
    blocos_processados: int = 0
    registros_lidos: int = 0
    registros_aprovados: int = 0
    duplicados_removidos: int = 0


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------

def _iterar_blocos(
    caminho: Path,
    chunk_size: int,
) -> Iterator[pd.DataFrame]:
    """Itera sobre o arquivo em blocos de ``chunk_size`` linhas.

    Args:
        caminho: Caminho do arquivo delimitado por ``;``.
        chunk_size: Número de linhas por bloco.

    Yields:
        Blocos de :class:`pandas.DataFrame` com as colunas oficiais.

    Raises:
        FileNotFoundError: Se o arquivo não existir.
        ValueError: Se o arquivo estiver vazio.

    Observações:
        - ``dtype=str`` é essencial para preservar zeros à esquerda em
          CNPJ, CEP, DDD, telefone e códigos.
        - ``keep_default_na=False`` evita converter ``"0"`` em ``NaN`` e
          textos vazios em ``NaN`` de forma surpreendente; normalizamos
          depois com o módulo ``validators``.
    """
    caminho = Path(caminho).expanduser().resolve()
    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo de entrada não encontrado: {caminho}")
    if caminho.stat().st_size == 0:
        raise ValueError("Arquivo de entrada está vazio.")

    # Verificamos se o arquivo tem conteúdo mínimo (uma linha).
    with open(caminho, "r", encoding="utf-8", errors="replace") as fp:
        if not fp.readline().strip():
            raise ValueError("Arquivo não contém linhas legíveis.")

    leitor = pd.read_csv(
        caminho,
        sep=";",
        header=None,
        names=COLUNAS_ESTABELECIMENTOS,
        dtype=str,
        chunksize=chunk_size,
        keep_default_na=False,
        na_values=[""],
        encoding="utf-8",
        encoding_errors="replace",
        quotechar='"',
        engine="python",  # engine Python é mais tolerante a campos irregulares
    )
    for bloco in leitor:
        yield bloco


def _enriquecer_bloco(bloco: pd.DataFrame) -> pd.DataFrame:
    """Adiciona colunas derivadas normalizadas a um bloco.

    Args:
        bloco: Bloco bruto lido do arquivo.

    Returns:
        Bloco com colunas ``CNPJ``, ``TIPO_ESTABELECIMENTO``,
        ``TELEFONE_FORMATADO``, ``EMAIL_NORMALIZADO``, ``CEP_NORMALIZADO``,
        ``DATA_ABERTURA``, ``ENDERECO_COMPLETO`` etc.

    Observações:
        - A aplicação linha-a-linha é feita com ``apply`` para manter o
          código legível; o volume total é limitado pelos filtros prévios
          e pelo uso de blocos.
    """
    if bloco.empty:
        return bloco

    # CNPJ completo (14 dígitos) e validado por estrutura.
    bloco["CNPJ"] = [
        montar_cnpj(b, o, d)
        for b, o, d in zip(
            bloco.get("CNPJ_BASICO", []),
            bloco.get("CNPJ_ORDEM", []),
            bloco.get("CNPJ_DV", []),
        )
    ]
    bloco["CNPJ_FORMATADO"] = bloco["CNPJ"].map(formatar_cnpj)

    # Tipo de estabelecimento legível.
    mapa_matriz = {"1": "Matriz", "2": "Filial"}
    bloco["TIPO_ESTABELECIMENTO"] = bloco.get(
        "MATRIZ_FILIAL", pd.Series(dtype=str)
    ).map(mapa_matriz).fillna("Desconhecido")

    # Telefone principal: priorizamos TELEFONE_1 com DDD_1; se ausente,
    # usamos TELEFONE_2 com DDD_2.
    telefones: list[Optional[str]] = []
    for ddd1, tel1, ddd2, tel2 in zip(
        bloco.get("DDD_1", []),
        bloco.get("TELEFONE_1", []),
        bloco.get("DDD_2", []),
        bloco.get("TELEFONE_2", []),
    ):
        normalizado = normalizar_telefone(ddd1, tel1) or normalizar_telefone(ddd2, tel2)
        telefones.append(normalizado)
    bloco["TELEFONE_NORMALIZADO"] = telefones
    bloco["TELEFONE_FORMATADO"] = [
        formatar_telefone(t) if t else None for t in telefones
    ]

    # E-mail normalizado (apenas trim/minúsculas; validação é feita nos
    # filtros, quando exigido).
    bloco["EMAIL_NORMALIZADO"] = bloco.get("EMAIL", pd.Series(dtype=str)).map(
        normalizar_email
    )

    # CEP normalizado (8 dígitos).
    bloco["CEP_NORMALIZADO"] = bloco.get("CEP", pd.Series(dtype=str)).map(
        normalizar_cep
    )

    # Datas convertidas para ``date`` quando válidas.
    bloco["DATA_ABERTURA"] = bloco.get(
        "DATA_INICIO_ATIVIDADE", pd.Series(dtype=str)
    ).map(converter_data_rfb)

    # Endereço completo concatenando componentes disponíveis.
    def _endereco_completo(row: pd.Series) -> Optional[str]:
        partes = [
            normalizar_endereco(row.get("TIPO_LOGRADOURO")),
            normalizar_endereco(row.get("LOGRADOURO")),
            normalizar_endereco(row.get("NUMERO")),
            normalizar_endereco(row.get("COMPLEMENTO")),
            normalizar_endereco(row.get("BAIRRO")),
        ]
        partes_validas = [p for p in partes if p]
        if not partes_validas:
            return None
        return ", ".join(partes_validas)

    bloco["ENDERECO_COMPLETO"] = bloco.apply(_endereco_completo, axis=1)

    return bloco


def processar_arquivo_em_blocos(
    caminho: Path,
    filtros: FiltroConfig,
    chunk_size: int = CHUNK_SIZE_PADRAO,
    callback_progresso: Optional[Callable[[int, int, int], None]] = None,
) -> ResultadoProcessamento:
    """Processa o arquivo de estabelecimentos em blocos com filtros.

    Args:
        caminho: Caminho do arquivo delimitado por ``;``.
        filtros: Configuração de filtros a aplicar.
        chunk_size: Número de linhas por bloco (padrão 200 000).
        callback_progresso: Função ``(indice_bloco, lidos, aprovados)``
            chamada após cada bloco.

    Returns:
        :class:`ResultadoProcessamento` com o DataFrame acumulado e métricas.

    Raises:
        FileNotFoundError: Se o arquivo não existir.
        ValueError: Se o arquivo estiver vazio ou ilegível.

    Observações:
        - Os filtros são aplicados bloco a bloco, reduzindo a memória
          necessária para arquivos nacionais grandes.
        - O DataFrame final concatena **apenas** as linhas aprovadas.
    """
    acumulado: list[pd.DataFrame] = []
    blocos = 0
    lidos = 0
    aprovados = 0

    for bloco in _iterar_blocos(caminho, chunk_size=chunk_size):
        blocos += 1
        lidos += len(bloco)

        bloco_enriquecido = _enriquecer_bloco(bloco)

        # Aplicamos os filtros já sobre o bloco enriquecido, para que
        # filtros dependam apenas de colunas normalizadas.
        bloco_filtrado = aplicar_filtros(bloco_enriquecido, filtros)

        if not bloco_filtrado.empty:
            acumulado.append(bloco_filtrado)
            aprovados += len(bloco_filtrado)

        if callback_progresso is not None:
            callback_progresso(blocos, lidos, aprovados)

    if acumulado:
        dataframe_final = pd.concat(acumulado, ignore_index=True)
    else:
        # DataFrame vazio mantendo as colunas enriquecidas para evitar
        # surpresas na camada de exibição/exportação.
        dataframe_final = pd.DataFrame(columns=COLUNAS_ESTABELECIMENTOS + [
            "CNPJ", "CNPJ_FORMATADO", "TIPO_ESTABELECIMENTO",
            "TELEFONE_NORMALIZADO", "TELEFONE_FORMATADO",
            "EMAIL_NORMALIZADO", "CEP_NORMALIZADO", "DATA_ABERTURA",
            "ENDERECO_COMPLETO",
        ])

    logger.info(
        "Processamento finalizado: blocos=%d lidos=%d aprovados=%d",
        blocos, lidos, aprovados,
    )

    return ResultadoProcessamento(
        dataframe=dataframe_final,
        blocos_processados=blocos,
        registros_lidos=lidos,
        registros_aprovados=aprovados,
        duplicados_removidos=0,
    )