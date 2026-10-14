"""
Interface Streamlit do Receita Explorer.

Responsabilidade:
    - Montar a interface web local.
    - Coordenar o fluxo: seleção de competência -> obtenção do arquivo ->
      processamento em blocos -> aplicação de filtros -> exibição dos
      resultados -> exportação.
    - Exibir métricas, avisos e erros de forma clara para o usuário.

A lógica de negócio (leitura, filtros, validação, exportação) permanece nos
módulos de ``src`` para manter baixo acoplamento entre interface e
processamento.
"""

from __future__ import annotations

import io
import json
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

from config.filtros import (
    CNAES_EXEMPLO,
    FILTROS_EXEMPLO,
    PALAVRAS_CHAVE_CLASSIFICACAO,
    PALAVRAS_CHAVE_EXCLUSAO_EXEMPLO,
    PALAVRAS_CHAVE_INCLUSAO_EXEMPLO,
    SITUACOES_CADASTRais,
    UFS_BRASIL,
    MUNICIPIO_EXEMPLO,
)
from src.downloader import (
    DownloadError,
    download_estabelecimentos,
    listar_arquivos_competencia,
)
from src.exporters import (
    exportar_csv,
    exportar_json_estatisticas,
    exportar_txt,
    exportar_xlsx,
)
from src.filters import (
    FiltroConfig,
    aplicar_filtros,
    classificar_dataframe,
    remover_duplicados,
)
from src.logger import configurar_logger
from src.reader import (
    COLUNAS_ESTABELECIMENTOS,
    ResultadoProcessamento,
    processar_arquivo_em_blocos,
)
from src.validators import normalizar_cnpj_formatado

logger = configurar_logger("receita_explorer.app")


# ---------------------------------------------------------------------------
# Constantes de UI
# ---------------------------------------------------------------------------

COMPETENCIA_PADRAO: str = "2026-10"
URL_COMPARTILHAMENTO_PADRAO: str = (
    "https://arquivos.receitafederal.gov.br/index.php/s/"
    "YggdBLfdninEJX9?dir=/2026-10"
)
CHUNK_SIZE_PADRAO: int = 200_000


# ---------------------------------------------------------------------------
# Estado da sessão
# ---------------------------------------------------------------------------

@dataclass
class EstadoSessao:
    """Encapsula o estado persistente da sessão Streamlit."""

    resultado: Optional[ResultadoProcessamento] = None
    resultados_classificados: Optional[pd.DataFrame] = None
    arquivo_origem: Optional[str] = None
    competencia: str = COMPETENCIA_PADRAO
    mensagens: list[tuple[str, str]] = field(default_factory=list)


def _obter_estado() -> EstadoSessao:
    """Recupera (ou cria) o estado da sessão.

    Returns:
        Instância de :class:`EstadoSessao` armazenada em ``st.session_state``.
    """
    if "estado" not in st.session_state:
        st.session_state["estado"] = EstadoSessao()
    return st.session_state["estado"]


# ---------------------------------------------------------------------------
# Sidebar: competência e origem do arquivo
# ---------------------------------------------------------------------------

def _sidebar_competencia() -> str:
    """Renderiza o seletor de competência.

    Returns:
        String da competência no formato ``AAAA-MM``.
    """
    st.sidebar.header("1. Competência dos dados")
    competencia = st.sidebar.text_input(
        "Competência (AAAA-MM)",
        value=COMPETENCIA_PADRAO,
        help=(
            "Informe a competência no formato AAAA-MM. A Receita Federal "
            "publica arquivos mensais; ajuste conforme a competência baixada."
        ),
    ).strip()

    if not competencia:
        st.sidebar.warning("Informe uma competência válida.")
        return COMPETENCIA_PADRAO
    try:
        ano, mes = competencia.split("-")
        if len(ano) != 4 or len(mes) != 2:
            raise ValueError
        datetime(int(ano), int(mes), 1)
    except (ValueError, TypeError):
        st.sidebar.error("Competência inválida. Use o formato AAAA-MM.")
        return COMPETENCIA_PADRAO
    return competencia


def _sidebar_origem_arquivo(competencia: str) -> Optional[Path]:
    """Permite escolher entre arquivo local e download automático.

    Args:
        competencia: Competência selecionada.

    Returns:
        Caminho para o arquivo a ser processado, ou ``None`` se nenhum estiver
        disponível.
    """
    st.sidebar.header("2. Arquivo de estabelecimentos")
    modo = st.sidebar.radio(
        "Origem do arquivo",
        options=("Importar arquivo local", "Tentar download automático"),
        index=0,
    )

    if modo == "Importar arquivo local":
        arquivo = st.sidebar.file_uploader(
            "Selecione o arquivo (deve conter 'ESTABELE' no nome idealmente)",
            type=None,
            accept_multiple_files=False,
        )
        if arquivo is None:
            return None

        # Persistimos o arquivo enviado em um diretório local de trabalho
        # para permitir processamento em blocos sem mantê-lo inteiramente em
        # memória. O arquivo é gravado fora do repositório (./data).
        destino_dir = Path("./data/uploads").resolve()
        destino_dir.mkdir(parents=True, exist_ok=True)
        destino = destino_dir / Path(arquivo.name).name
        with open(destino, "wb") as fp:
            fp.write(arquivo.getbuffer())
        st.sidebar.success(f"Arquivo carregado: {destino.name}")
        return destino

    # Modo download automático
    st.sidebar.caption(
        "O download automático depende da estrutura da página de "
        "compartilhamento da Receita Federal."
    )
    url = st.sidebar.text_input("URL da competência", value=URL_COMPARTILHAMENTO_PADRAO)
    limite_mb = st.sidebar.number_input(
        "Limite de download (MB)",
        min_value=1,
        max_value=20_000,
        value=2048,
        step=128,
    )

    if st.sidebar.button("Listar arquivos da competência"):
        try:
            arquivos = listar_arquivos_competencia(url)
        except DownloadError as exc:
            st.sidebar.error(f"Falha ao listar: {exc}")
            return None
        if not arquivos:
            st.sidebar.warning(
                "Nenhum link direto foi identificado. Baixe manualmente o "
                "arquivo de estabelecimentos e use a opção de importação."
            )
            return None
        st.session_state["arquivos_disponiveis"] = arquivos
        st.sidebar.success(f"{len(arquivos)} arquivo(s) identificado(s).")

    arquivos_disponiveis = st.session_state.get("arquivos_disponiveis") or []
    if arquivos_disponiveis:
        escolha = st.sidebar.selectbox(
            "Arquivo",
            options=arquivos_disponiveis,
            format_func=lambda a: a.nome,
        )
        if st.sidebar.button("Baixar arquivo selecionado"):
            try:
                destino = download_estabelecimentos(
                    escolha,
                    destino_dir=Path("./data/downloads"),
                    max_bytes=int(limite_mb) * 1024 * 1024,
                    competencia=competencia,
                    progresso_callback=lambda lidos, total: st.sidebar.progress(
                        min(1.0, lidos / total) if total else 0.0,
                        text=f"{lidos:,} / {total:,} bytes",
                    ),
                )
            except DownloadError as exc:
                st.sidebar.error(f"Falha no download: {exc}")
                return None
            st.sidebar.success(f"Arquivo salvo em {destino.name}")
            return destino
    return None


# ---------------------------------------------------------------------------
# Sidebar: filtros
# ---------------------------------------------------------------------------

def _sidebar_filtros() -> FiltroConfig:
    """Renderiza os controles de filtros.

    Returns:
        Instância de :class:`FiltroConfig` preenchida com os valores da UI.
    """
    st.sidebar.header("3. Filtros")

    uf = st.sidebar.selectbox(
        "UF",
        options=[""] + UFS_BRASIL,
        index=0,
        help="Filtra por UF do estabelecimento. Vazio = qualquer UF.",
    )

    municipio_codigo = st.sidebar.text_input(
        "Código do município (RFB)",
        value=MUNICIPIO_EXEMPLO,
        help=(
            "Código de 7 dígitos da tabela oficial de municípios da Receita "
            "Federal. Exemplo: Goiânia-GO = 5208707."
        ),
    ).strip()

    situacoes = st.sidebar.multiselect(
        "Situação cadastral",
        options=list(SITUACOES_CADASTRais.keys()),
        default=[],
        format_func=lambda c: f"{c} - {SITUACOES_CADASTRais[c]}",
    )

    cnae_principal = st.sidebar.text_input(
        "CNAE principal (prefixo)",
        value="",
        help="Filtra estabelecimentos cujo CNAE principal comece com este prefixo.",
    ).strip()

    cnaes_interesse_txt = st.sidebar.text_area(
        "CNAEs de interesse (um por linha)",
        value="\n".join(CNAES_EXEMPLO[:5]),
        help=(
            "Um código por linha. O CNAE pode estar no principal ou nos "
            "secundários. Vazio = não filtrar por esta lista."
        ),
    )
    cnaes_interesse = [
        linha.strip()
        for linha in cnaes_interesse_txt.splitlines()
        if linha.strip()
    ]

    palavras_incluir_txt = st.sidebar.text_area(
        "Palavras-chave incluídas (uma por linha)",
        value="\n".join(PALAVRAS_CHAVE_INCLUSAO_EXEMPLO),
        help="Nome fantasia deve conter ao menos uma delas (lógica OR).",
    )
    palavras_incluir = [
        linha.strip()
        for linha in palavras_incluir_txt.splitlines()
        if linha.strip()
    ]

    palavras_excluir_txt = st.sidebar.text_area(
        "Palavras-chave excluídas (uma por linha)",
        value="\n".join(PALAVRAS_CHAVE_EXCLUSAO_EXEMPLO),
        help="Se o nome fantasia contiver qualquer uma delas, o registro é descartado.",
    )
    palavras_excluir = [
        linha.strip()
        for linha in palavras_excluir_txt.splitlines()
        if linha.strip()
    ]

    exigir_telefone = st.sidebar.checkbox("Exigir telefone", value=False)
    exigir_email = st.sidebar.checkbox("Exigir e-mail", value=False)

    col_a, col_b = st.sidebar.columns(2)
    with col_a:
        data_ini = st.date_input("Início atividade >= ", value=None)
    with col_b:
        data_fim = st.date_input("Início atividade <= ", value=None)

    nome_fantasia = st.sidebar.text_input(
        "Nome fantasia (contém)",
        value="",
        help="Correspondência parcial, sem diferenciar maiúsculas/minúsculas.",
    ).strip()

    cnpj_busca = st.sidebar.text_input(
        "CNPJ (com ou sem máscara)",
        value="",
        help="Se informado, busca o CNPJ completo (14 dígitos).",
    ).strip()

    combinacao = st.sidebar.radio(
        "Combinação entre grupos de filtros",
        options=("AND", "OR"),
        index=0,
        help=(
            "AND: todas as condições precisam ser satisfeitas. "
            "OR: basta satisfazer uma das condições informadas."
        ),
    )

    return FiltroConfig(
        uf=uf or None,
        municipio_codigo=municipio_codigo or None,
        situacoes=list(situacoes) or None,
        cnae_principal_prefixo=cnae_principal or None,
        cnaes_interesse=cnaes_interesse or None,
        palavras_chave_incluir=palavras_incluir or None,
        palavras_chave_excluir=palavras_excluir or None,
        exigir_telefone=exigir_telefone,
        exigir_email=exigir_email,
        data_inicio_atividade_min=data_ini,
        data_inicio_atividade_max=data_fim,
        nome_fantasia_contem=nome_fantasia or None,
        cnpj_completo=cnpj_busca or None,
        combinacao=combinacao,
    )


# ---------------------------------------------------------------------------
# Painel de classificação
# ---------------------------------------------------------------------------

def _sidebar_classificacao() -> dict[str, list[str]]:
    """Permite ajustar as palavras-chave de classificação por categoria.

    Returns:
        Dicionário ``{categoria: [palavras]}``.
    """
    st.sidebar.header("4. Classificação por palavras-chave")
    st.sidebar.caption(
        "As categorias são aplicadas ao nome fantasia em ordem de "
        "precedência. Ajuste as listas se necessário."
    )

    configuracoes: dict[str, list[str]] = {}
    for categoria, termos in PALAVRAS_CHAVE_CLASSIFICACAO.items():
        texto = st.sidebar.text_area(
            f"{categoria}",
            value=", ".join(termos),
            key=f"classif_{categoria}",
            height=60,
        )
        configuracoes[categoria] = [
            t.strip() for t in texto.split(",") if t.strip()
        ]
    return configuracoes


# ---------------------------------------------------------------------------
# Execução do processamento
# ---------------------------------------------------------------------------

def _executar_processamento(
    arquivo: Path,
    competencia: str,
    filtros: FiltroConfig,
    classificacao: dict[str, list[str]],
    chunk_size: int,
) -> None:
    """Executa o processamento em blocos e armazena o resultado no estado.

    Args:
        arquivo: Caminho do arquivo de estabelecimentos.
        competencia: Competência selecionada.
        filtros: Configuração de filtros.
        classificacao: Palavras-chave por categoria.
        chunk_size: Tamanho do bloco de leitura.
    """
    estado = _obter_estado()
    estado.mensagens.clear()

    progresso = st.progress(0.0, text="Iniciando processamento...")
    status_txt = st.empty()
    metrics_area = st.empty()

    inicio = time.perf_counter()

    def _on_bloco(indice: int, lidos: int, aprovados: int) -> None:
        # Atualizamos a barra sem inventar totais: usamos o número do bloco e
        # contadores efetivos. Como não conhecemos o total de linhas do
        # arquivo antes de ler, mostramos um progresso indeterminado textual.
        status_txt.text(
            f"Bloco {indice}: {lidos:,} registros lidos, "
            f"{aprovados:,} aprovados nos filtros."
        )
        progresso.progress(min(0.99, indice * 0.01), text="Processando...")

    try:
        logger.info("Iniciando processamento: arquivo=%s competencia=%s",
                    arquivo.name, competencia)
        resultado = processar_arquivo_em_blocos(
            caminho=arquivo,
            filtros=filtros,
            chunk_size=chunk_size,
            callback_progresso=_on_bloco,
        )
    except Exception as exc:  # noqa: BLE001 - queremos reportar ao usuário
        logger.exception("Falha no processamento do arquivo.")
        progresso.empty()
        status_txt.empty()
        st.error(f"Falha ao processar o arquivo: {exc}")
        return

    duracao = time.perf_counter() - inicio

    # Remoção de duplicados
    antes = len(resultado.dataframe)
    df_sem_dup = remover_duplicados(resultado.dataframe)
    removidos = antes - len(df_sem_dup)
    resultado.duplicados_removidos = removidos
    resultado.dataframe = df_sem_dup

    # Classificação por palavras-chave
    df_classificado = classificar_dataframe(df_sem_dup, classificacao)

    estado.resultado = resultado
    estado.resultados_classificados = df_classificado
    estado.arquivo_origem = arquivo.name
    estado.competencia = competencia

    logger.info(
        "Processamento concluído em %.2fs: lidos=%d aprovados=%d duplicados_removidos=%d",
        duracao,
        resultado.registros_lidos,
        resultado.registros_aprovados,
        removidos,
    )

    progresso.progress(1.0, text="Concluído.")
    status_txt.text(
        f"Concluído em {duracao:.2f}s. "
        f"Blocos: {resultado.blocos_processados} | "
        f"Lidos: {resultado.registros_lidos:,} | "
        f"Aprovados: {resultado.registros_aprovados:,} | "
        f"Duplicados removidos: {removidos:,}"
    )

    with metrics_area.container():
        _render_metricas(resultado, df_classificado, duracao)


def _render_metricas(
    resultado: ResultadoProcessamento,
    df_classificado: pd.DataFrame,
    duracao: float,
) -> None:
    """Exibe as métricas efetivamente calculadas.

    Args:
        resultado: Resultado do processamento em blocos.
        df_classificado: DataFrame após classificação e remoção de duplicados.
        duracao: Duração total do processamento em segundos.
    """
    total = len(df_classificado)
    com_tel = int(df_classificado.get("TELEFONE_FORMATADO", pd.Series(dtype=str)).notna().sum()) if total else 0
    com_email = int(df_classificado.get("EMAIL", pd.Series(dtype=str)).notna().sum()) if total else 0
    empresas_unicas = (
        df_classificado["CNPJ"].nunique() if "CNPJ" in df_classificado.columns else 0
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Blocos processados", f"{resultado.blocos_processados:,}")
    c2.metric("Registros lidos", f"{resultado.registros_lidos:,}")
    c3.metric("Registros aprovados", f"{resultado.registros_aprovados:,}")
    c4.metric("Duplicados removidos", f"{resultado.duplicados_removidos:,}")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Empresas no resultado", f"{empresas_unicas:,}")
    c6.metric("Com telefone", f"{com_tel:,}")
    c7.metric("Com e-mail", f"{com_email:,}")
    c8.metric("Duração (s)", f"{duracao:.2f}")


# ---------------------------------------------------------------------------
# Tabela de resultados e exportação
# ---------------------------------------------------------------------------

COLUNAS_EXIBICAO: list[str] = [
    "CNPJ",
    "TIPO_ESTABELECIMENTO",
    "NOME_FANTASIA",
    "DATA_INICIO_ATIVIDADE",
    "CNAE_PRINCIPAL",
    "LOGRADOURO",
    "NUMERO",
    "COMPLEMENTO",
    "BAIRRO",
    "CEP",
    "MUNICIPIO",
    "UF",
    "TELEFONE_FORMATADO",
    "EMAIL",
    "CATEGORIA_CLASSIFICADA",
]


def _render_resultados() -> None:
    """Renderiza a tabela de resultados e os botões de exportação."""
    estado = _obter_estado()
    if estado.resultados_classificados is None:
        st.info("Nenhum resultado disponível. Execute o processamento primeiro.")
        return

    df = estado.resultados_classificados
    if df.empty:
        st.warning("O processamento terminou sem registros após os filtros.")
        return

    st.subheader("Resultados")
    st.caption(
        "Você pode ordenar clicando nos cabeçalhos e usar a busca do "
        "Streamlit para filtrar a visualização."
    )

    colunas_presentes = [c for c in COLUNAS_EXIBICAO if c in df.columns]
    st.dataframe(df[colunas_presentes], use_container_width=True, height=500)

    st.subheader("Exportação")
    escopo = st.radio(
        "Escopo da exportação",
        options=("Todos os resultados", "Somente o que está visível"),
        index=0,
    )

    # Como o Streamlit não expõe com facilidade as linhas filtradas por
    # pesquisa no widget, usamos "todos" ou "primeiros N" quando o usuário
    # quer uma amostra. Documentamos essa limitação na interface.
    if escopo == "Somente o que está visível":
        limite = st.number_input(
            "Quantidade de linhas visíveis a exportar",
            min_value=1,
            max_value=max(1, len(df)),
            value=min(1000, len(df)),
            step=100,
        )
        df_export = df.head(int(limite))
    else:
        df_export = df

    competencia = estado.competencia
    identificador = datetime.now().strftime("%Y%m%d-%H%M%S")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button("Gerar CSV"):
            try:
                conteudo = exportar_csv(df_export)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Falha ao gerar CSV.")
                st.error(f"Falha ao gerar CSV: {exc}")
            else:
                st.download_button(
                    "Baixar CSV",
                    data=conteudo,
                    file_name=f"receita-explorer_{competencia}_{identificador}.csv",
                    mime="text/csv",
                )

    with col2:
        if st.button("Gerar XLSX"):
            try:
                conteudo = exportar_xlsx(df_export)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Falha ao gerar XLSX.")
                st.error(f"Falha ao gerar XLSX: {exc}")
            else:
                st.download_button(
                    "Baixar XLSX",
                    data=conteudo,
                    file_name=f"receita-explorer_{competencia}_{identificador}.xlsx",
                    mime=(
                        "application/vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet"
                    ),
                )

    with col3:
        if st.button("Gerar TXT"):
            try:
                conteudo = exportar_txt(df_export, competencia=competencia)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Falha ao gerar TXT.")
                st.error(f"Falha ao gerar TXT: {exc}")
            else:
                st.download_button(
                    "Baixar TXT",
                    data=conteudo,
                    file_name=f"receita-explorer_{competencia}_{identificador}.txt",
                    mime="text/plain",
                )

    with col4:
        if st.button("Gerar JSON (estatísticas)"):
            try:
                estatisticas = _estatisticas(df_export, competencia)
                conteudo = exportar_json_estatisticas(estatisticas)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Falha ao gerar JSON.")
                st.error(f"Falha ao gerar JSON: {exc}")
            else:
                st.download_button(
                    "Baixar JSON",
                    data=conteudo,
                    file_name=f"receita-explorer_{competencia}_{identificador}.json",
                    mime="application/json",
                )


def _estatisticas(df: pd.DataFrame, competencia: str) -> dict:
    """Monta o dicionário de estatísticas exportado como JSON.

    Args:
        df: DataFrame final.
        competencia: Competência selecionada.

    Returns:
        Dicionário serializável em JSON.
    """
    total = len(df)
    resultado: dict = {
        "competencia": competencia,
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "total_registros": total,
    }
    if total == 0:
        return resultado

    if "UF" in df.columns:
        resultado["por_uf"] = df["UF"].value_counts().to_dict()
    if "CATEGORIA_CLASSIFICADA" in df.columns:
        resultado["por_categoria"] = (
            df["CATEGORIA_CLASSIFICADA"].value_counts().to_dict()
        )
    if "SITUACAO_CADASTRAL" in df.columns:
        resultado["por_situacao_cadastral"] = (
            df["SITUACAO_CADASTRAL"].value_counts().to_dict()
        )
    resultado["com_telefone"] = int(
        df.get("TELEFONE_FORMATADO", pd.Series(dtype=str)).notna().sum()
    )
    resultado["com_email"] = int(
        df.get("EMAIL", pd.Series(dtype=str)).notna().sum()
    )
    return resultado


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Ponto de entrada da aplicação Streamlit."""
    st.set_page_config(
        page_title="Receita Explorer",
        page_icon="🔎",
        layout="wide",
    )

    st.title("Receita Explorer")
    st.markdown(
        "Aplicação local para **importar, filtrar, classificar e exportar** "
        "dados públicos de estabelecimentos empresariais da Receita Federal "
        "do Brasil."
    )

    st.sidebar.title("Receita Explorer")
    st.sidebar.caption(
        "Use dados empresariais públicos com responsabilidade. "
        "Consulte `docs/privacidade-e-uso.md`."
    )

    competencia = _sidebar_competencia()
    arquivo = _sidebar_origem_arquivo(competencia)
    filtros = _sidebar_filtros()
    classificacao = _sidebar_classificacao()

    chunk_size = st.sidebar.number_input(
        "Tamanho do bloco (linhas)",
        min_value=10_000,
        max_value=2_000_000,
        value=CHUNK_SIZE_PADRAO,
        step=10_000,
        help=(
            "Número de linhas por bloco de leitura. Blocos menores reduzem "
            "o consumo de memória ao custo de mais I/O."
        ),
    )

    st.sidebar.header("5. Executar")
    executar = st.sidebar.button("Processar arquivo", type="primary")

    if executar:
        if arquivo is None:
            st.error(
                "Nenhum arquivo disponível. Importe um arquivo local ou "
                "conclua o download automático antes de processar."
            )
        else:
            _executar_processamento(
                arquivo=arquivo,
                competencia=competencia,
                filtros=filtros,
                classificacao=classificacao,
                chunk_size=int(chunk_size),
            )

    _render_resultados()

    with st.expander("Sobre o layout e a origem dos dados"):
        st.markdown(
            "- Fonte: arquivos públicos de CNPJ da Receita Federal do Brasil.\n"
            "- O layout de estabelecimentos possui 30 colunas separadas por `;`.\n"
            "- A ordem é documentada em `docs/fonte-dos-dados.md`.\n"
            "- A URL de compartilhamento **não** é um link direto de download."
        )

    with st.expander("Colunas lidas do arquivo"):
        st.write(COLUNAS_ESTABELECIMENTOS)

    with st.expander("Mensagens recentes"):
        estado = _obter_estado()
        if not estado.mensagens:
            st.write("Sem mensagens.")
        for nivel, msg in estado.mensagens:
            st.write(f"[{nivel}] {msg}")


if __name__ == "__main__":
    main()