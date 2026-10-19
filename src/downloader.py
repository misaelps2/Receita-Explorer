"""
Download e identificação de arquivos públicos da Receita Federal.

Responsabilidade:
    - Identificar, quando possível, links diretos de arquivos hospedados na
      página de compartilhamento da Receita Federal.
    - Realizar download em streaming, com verificação de tamanho e sem
      carregar o arquivo inteiro em memória.
    - Tratar redirecionamentos, falhas HTTP, timeouts e interrupções.
    - Nunca afirmar sucesso sem verificar o resultado gravado em disco.

Observações importantes:
    - A página de compartilhamento informada no projeto
      (``https://arquivos.receitafederal.gov.br/index.php/s/...``) **não** é
      um link direto de download. Este módulo tenta descobrir links diretos
      com base em padrões usuais do Nextcloud (``/download``), mas não
      inventa endpoints. Se a descoberta falhar, o usuário deve baixar o
      arquivo manualmente e usar a importação local.
    - Não baixamos a base nacional inteira: apenas o arquivo selecionado.
    - Não executamos nada do conteúdo baixado; apenas gravamos em disco.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional
from urllib.parse import urljoin, urlparse

import requests

from src.logger import configurar_logger

logger = configurar_logger("receita_explorer.downloader")


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# Padrão de nome de arquivo de estabelecimentos publicado pela RFB.
# Historicamente algo como ``K3241.K03200Y0.D90610.ESTABELE``.
_REGEX_ESTABELE = re.compile(r"ESTABELE", re.IGNORECASE)

# Timeout padrão (conexão, leitura) em segundos.
_TIMEOUT_PADRAO = (15, 60)

# User-Agent simples e honesto.
_USER_AGENT = "receita-explorer/0.1 (+https://github.com/)"


# ---------------------------------------------------------------------------
# Exceções
# ---------------------------------------------------------------------------

class DownloadError(Exception):
    """Erro genérico relacionado a download ou identificação de arquivos."""


# ---------------------------------------------------------------------------
# Estruturas
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ArquivoRemoto:
    """Representa um arquivo remoto candidato a download.

    Attributes:
        nome: Nome do arquivo exibido na interface.
        url_direta: URL direta de download, quando identificada.
        url_origem: URL da página de compartilhamento onde foi encontrado.
    """

    nome: str
    url_direta: str
    url_origem: str


# ---------------------------------------------------------------------------
# Descoberta de arquivos
# ---------------------------------------------------------------------------

def _sessao_http() -> requests.Session:
    """Cria uma :class:`requests.Session` com cabeçalhos padrão.

    Returns:
        Sessão HTTP reutilizável.
    """
    sessao = requests.Session()
    sessao.headers.update({"User-Agent": _USER_AGENT})
    return sessao


def _resolver_url_direta(url_compartilhamento: str, nome_arquivo: str) -> str:
    """Tenta construir uma URL direta plausível para um arquivo do Nextcloud.

    Args:
        url_compartilhamento: URL da página de compartilhamento.
        nome_arquivo: Nome do arquivo desejado.

    Returns:
        URL candidata para download direto.

    Observações:
        - O Nextcloud costuma expor arquivos via ``/download?path=...&files=...``.
          Aqui montamos uma URL candidata combinando o diretório da página
          com o parâmetro ``files=``. Esta função **não** garante que a URL
          responde; a verificação é feita por :func:`_verificar_url_direta`.
    """
    parsed = urlparse(url_compartilhamento)
    # Extrai o diretório atual a partir de ``?dir=/AAAA-MM`` se presente.
    diretorio = ""
    if parsed.query:
        for parte in parsed.query.split("&"):
            if parte.startswith("dir="):
                diretorio = parte[len("dir="):]
                break

    # Base até o token do compartilhamento: /index.php/s/<token>
    base = f"{parsed.scheme}://{parsed.netloc}"
    caminho = parsed.path
    token_match = re.match(r"^(/index\.php/s/[^/]+)", caminho)
    if not token_match:
        # Não é um compartilhamento Nextcloud reconhecível.
        return url_compartilhamento
    token_path = token_match.group(1)

    # Monta a URL candidata usando o endpoint público de download do
    # Nextcloud. Se o servidor não aceitar, o HEAD/GET de verificação falha
    # e o arquivo não é oferecido ao usuário.
    candidata = (
        f"{base}{token_path}/download"
        f"?path={diretorio}&files={nome_arquivo}"
    )
    return candidata


def _verificar_url_direta(
    sessao: requests.Session,
    url: str,
    max_bytes: Optional[int] = None,
) -> Optional[int]:
    """Verifica se uma URL responde como download válido.

    Args:
        sessao: Sessão HTTP.
        url: URL candidata.
        max_bytes: Tamanho máximo aceitável em bytes (opcional).

    Returns:
        Tamanho em bytes se a verificação for bem-sucedida, ``None`` caso
        contrário.

    Observações:
        - Enviamos HEAD primeiro. Se o servidor não suportar HEAD (405),
          caímos para GET com ``stream=True`` e abortamos a leitura
          imediatamente.
    """
    try:
        resp = sessao.head(url, allow_redirects=True, timeout=_TIMEOUT_PADRAO)
        if resp.status_code == 405:
            resp = sessao.get(
                url, allow_redirects=True, timeout=_TIMEOUT_PADRAO, stream=True
            )
            resp.close()
        if resp.status_code != 200:
            return None
        tamanho_header = resp.headers.get("Content-Length")
        tamanho = int(tamanho_header) if tamanho_header and tamanho_header.isdigit() else None
        if tamanho is None:
            return None
        if max_bytes is not None and tamanho > max_bytes:
            logger.warning(
                "Arquivo %s excede limite (%s > %s bytes).",
                url, tamanho, max_bytes,
            )
            return None
        return tamanho
    except requests.RequestException as exc:
        logger.info("Verificação de URL falhou: %s (%s)", url, exc)
        return None


def listar_arquivos_competencia(
    url_compartilhamento: str,
    max_bytes: Optional[int] = None,
) -> list[ArquivoRemoto]:
    """Tenta listar arquivos de estabelecimentos da competência informada.

    Args:
        url_compartilhamento: URL da página de compartilhamento.
        max_bytes: Limite opcional de tamanho aceitável por arquivo.

    Returns:
        Lista de :class:`ArquivoRemoto` para arquivos cujo nome contenha
        ``ESTABELE`` e cuja URL direta candidata responde a HEAD/GET.

    Raises:
        DownloadError: Se a página de compartilhamento não puder ser
            acessada ou se nenhum arquivo compatível for identificado.

    Observações:
        - Esta função **não** inventa nomes de arquivo. Ela apenas tenta
          derivar nomes plausíveis a partir do padrão histórico e testa se
          a URL direta responde. Se não for possível, retorna lista vazia
          (a interface orienta o usuário a baixar manualmente).
    """
    sessao = _sessao_http()
    try:
        resp = sessao.get(
            url_compartilhamento,
            allow_redirects=True,
            timeout=_TIMEOUT_PADRAO,
        )
    except requests.RequestException as exc:
        raise DownloadError(f"Falha ao acessar a página de compartilhamento: {exc}") from exc

    if resp.status_code != 200:
        raise DownloadError(
            f"Página de compartilhamento respondeu HTTP {resp.status_code}."
        )

    # Extraímos candidatos de nome a partir de links âncora que contenham
    # "ESTABELE" no texto. Se não houver nenhum, retornamos lista vazia.
    html = resp.text
    candidatos: set[str] = set()
    for match in re.finditer(
        r'href="[^"]*?([^"/]+?ESTABELE[^"/]*?)"', html, re.IGNORECASE
    ):
        candidatos.add(match.group(1))

    arquivos: list[ArquivoRemoto] = []
    for nome in sorted(candidatos):
        url_direta = _resolver_url_direta(url_compartilhamento, nome)
        tamanho = _verificar_url_direta(sessao, url_direta, max_bytes=max_bytes)
        if tamanho is None:
            logger.info("URL direta não confirmada para %s; ignorando.", nome)
            continue
        arquivos.append(
            ArquivoRemoto(
                nome=nome,
                url_direta=url_direta,
                url_origem=url_compartilhamento,
            )
        )

    if not arquivos:
        logger.warning(
            "Nenhum arquivo ESTABELE com URL direta confirmada em %s.",
            url_compartilhamento,
        )
    return arquivos


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def _nome_seguro(nome: str) -> str:
    """Sanitiza o nome de arquivo para uso em disco.

    Args:
        nome: Nome original.

    Returns:
        Nome sem separadores de caminho e sem caracteres problemáticos.
    """
    nome = os.path.basename(nome)
    nome = re.sub(r"[^\w.\-]+", "_", nome)
    return nome or "arquivo"


def download_estabelecimentos(
    arquivo: ArquivoRemoto,
    destino_dir: Path,
    max_bytes: int,
    competencia: str,
    progresso_callback: Optional[Callable[[int, int], None]] = None,
    sobrescrever: bool = False,
) -> Path:
    """Baixa um arquivo de estabelecimentos em streaming.

    Args:
        arquivo: Instância de :class:`ArquivoRemoto`.
        destino_dir: Diretório onde o arquivo será gravado.
        max_bytes: Tamanho máximo permitido em bytes.
        competencia: Competência (usada apenas em log/feedback).
        progresso_callback: Função ``(bytes_lidos, bytes_total)`` chamada
            periodicamente durante o download.
        sobrescrever: Se ``False`` e o arquivo já existir, apenas reutiliza.

    Returns:
        Caminho do arquivo baixado (ou reutilizado).

    Raises:
        DownloadError: Em caso de falha HTTP, interrupção, arquivo grande
            demais ou resposta inconsistente.

    Observações:
        - O download é gravado em arquivo temporário ``*.parcial`` e movido
          para o destino final somente após verificação.
    """
    destino_dir = Path(destino_dir).expanduser().resolve()
    destino_dir.mkdir(parents=True, exist_ok=True)
    nome_limpo = _nome_seguro(arquivo.nome)
    destino_final = destino_dir / f"{competencia}_{nome_limpo}"

    if destino_final.exists() and not sobrescrever:
        logger.info("Reutilizando arquivo já baixado: %s", destino_final.name)
        return destino_final

    destino_parcial = destino_final.with_suffix(destino_final.suffix + ".parcial")

    sessao = _sessao_http()
    try:
        with sessao.get(
            arquivo.url_direta,
            stream=True,
            allow_redirects=True,
            timeout=_TIMEOUT_PADRAO,
        ) as resp:
            if resp.status_code != 200:
                raise DownloadError(
                    f"Servidor respondeu HTTP {resp.status_code} ao baixar "
                    f"{arquivo.nome}."
                )

            tamanho_header = resp.headers.get("Content-Length")
            total = int(tamanho_header) if tamanho_header and tamanho_header.isdigit() else 0
            if total and total > max_bytes:
                raise DownloadError(
                    f"Arquivo tem {total} bytes, acima do limite de "
                    f"{max_bytes} bytes."
                )

            lidos = 0
            with open(destino_parcial, "wb") as fp:
                for bloco in resp.iter_content(chunk_size=1024 * 1024):
                    if not bloco:
                        continue
                    lidos += len(bloco)
                    if lidos > max_bytes:
                        raise DownloadError(
                            "Download excedeu o limite configurado; abortando."
                        )
                    fp.write(bloco)
                    if progresso_callback is not None:
                        progresso_callback(lidos, total)

    except requests.RequestException as exc:
        if destino_parcial.exists():
            destino_parcial.unlink(missing_ok=True)
        raise DownloadError(f"Falha de rede durante o download: {exc}") from exc
    except Exception:
        if destino_parcial.exists():
            destino_parcial.unlink(missing_ok=True)
        raise

    # Verificações finais antes de confirmar o sucesso.
    if not destino_parcial.exists() or destino_parcial.stat().st_size == 0:
        destino_parcial.unlink(missing_ok=True)
        raise DownloadError("Arquivo baixado está vazio; download descartado.")

    if total and destino_parcial.stat().st_size != total:
        # Verificação de comprimento; pode haver compressão em trânsito, mas
        # como o Nextcloud entrega o arquivo tal como está, exigimos
        # igualdade quando Content-Length foi informado.
        tamanho_real = destino_parcial.stat().st_size
        destino_parcial.unlink(missing_ok=True)
        raise DownloadError(
            f"Tamanho baixado ({tamanho_real}) difere do esperado ({total})."
        )

    destino_parcial.replace(destino_final)
    logger.info(
        "Download concluído: %s (%d bytes) competencia=%s",
        destino_final.name, destino_final.stat().st_size, competencia,
    )
    return destino_final


def importar_arquivo_local(origem: Path, destino_dir: Path, competencia: str) -> Path:
    """Copia um arquivo local informado pelo usuário para o diretório de dados.

    Args:
        origem: Caminho do arquivo local.
        destino_dir: Diretório de destino (fora do Git).
        competencia: Competência associada.

    Returns:
        Caminho do arquivo copiado.

    Raises:
        DownloadError: Se o arquivo de origem não existir ou estiver vazio.
    """
    origem = Path(origem).expanduser().resolve()
    if not origem.exists():
        raise DownloadError(f"Arquivo não encontrado: {origem}")
    if origem.stat().st_size == 0:
        raise DownloadError("Arquivo de origem está vazio.")

    destino_dir = Path(destino_dir).expanduser().resolve()
    destino_dir.mkdir(parents=True, exist_ok=True)
    destino = destino_dir / f"{competencia}_{_nome_seguro(origem.name)}"

    with open(origem, "rb") as fp_in, open(destino, "wb") as fp_out:
        while True:
            bloco = fp_in.read(1024 * 1024)
            if not bloco:
                break
            fp_out.write(bloco)

    logger.info("Arquivo local importado: %s -> %s", origem.name, destino.name)
    return destino


__all__: Iterable[str] = (
    "ArquivoRemoto",
    "DownloadError",
    "download_estabelecimentos",
    "importar_arquivo_local",
    "listar_arquivos_competencia",
)