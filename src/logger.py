"""
Configuração centralizada de logging do Receita Explorer.

Responsabilidade:
    - Fornecer um logger padronizado com formatação consistente.
    - Gravar logs em arquivo local (fora do Git) e no console.
    - Evitar duplicação de handlers quando o módulo é importado várias vezes.

Observações:
    - Os logs são gravados por padrão em ``./logs/receita_explorer.log``.
    - Este módulo não registra listas de CNPJs, telefones ou e-mails.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional


_FORMATO_PADRAO = (
    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)
_FORMATO_DATA = "%Y-%m-%d %H:%M:%S"

# Guardamos referência aos loggers já configurados para evitar adicionar
# handlers duplicados quando ``configurar_logger`` é chamado múltiplas vezes.
_loggers_configurados: set[str] = set()


def _diretorio_logs() -> Path:
    """Determina o diretório de logs, respeitando variável de ambiente.

    Returns:
        Caminho absoluto para o diretório de logs.
    """
    base = os.environ.get("RECEITA_EXPLORER_LOG_DIR", "./logs")
    caminho = Path(base).expanduser().resolve()
    caminho.mkdir(parents=True, exist_ok=True)
    return caminho


def configurar_logger(
    nome: str = "receita_explorer",
    nivel: int = logging.INFO,
    arquivo: Optional[Path] = None,
) -> logging.Logger:
    """Configura e retorna um logger padronizado.

    Args:
        nome: Nome do logger (usualmente ``__name__`` do módulo).
        nivel: Nível mínimo de logging (padrão ``logging.INFO``).
        arquivo: Caminho opcional do arquivo de log. Se ``None``, usa
            ``./logs/receita_explorer.log``.

    Returns:
        Instância de :class:`logging.Logger` configurada.

    Observações:
        - Chamadas repetidas com o mesmo ``nome`` são idempotentes.
        - O logger não propaga para o root logger, evitando duplicação.
    """
    logger = logging.getLogger(nome)

    if nome in _loggers_configurados:
        return logger

    logger.setLevel(nivel)
    logger.propagate = False

    formato = logging.Formatter(_FORMATO_PADRAO, datefmt=_FORMATO_DATA)

    # Handler de console
    handler_console = logging.StreamHandler(stream=sys.stderr)
    handler_console.setLevel(nivel)
    handler_console.setFormatter(formato)
    logger.addHandler(handler_console)

    # Handler de arquivo
    destino = arquivo or (_diretorio_logs() / "receita_explorer.log")
    try:
        handler_arquivo = logging.FileHandler(destino, encoding="utf-8")
    except OSError as exc:
        # Não interrompemos a aplicação apenas por falha ao abrir o arquivo
        # de log; emitimos aviso no console.
        logger.warning("Não foi possível abrir arquivo de log %s: %s", destino, exc)
    else:
        handler_arquivo.setLevel(nivel)
        handler_arquivo.setFormatter(formato)
        logger.addHandler(handler_arquivo)

    _loggers_configurados.add(nome)
    return logger