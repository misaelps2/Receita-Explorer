"""
Pacote principal do Receita Explorer.

Reúne os módulos de lógica de negócio (leitura, filtros, validação,
exportação, download e logging) mantendo a interface Streamlit em ``app.py``
separada das responsabilidades de processamento.
"""

__all__ = [
    "downloader",
    "exporters",
    "filters",
    "logger",
    "reader",
    "validators",
]