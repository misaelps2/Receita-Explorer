"""
Configurações iniciais de filtros, CNAEs, palavras-chave e constantes.

Responsabilidade:
    - Centralizar valores padrão usados pela interface e pelos testes.
    - Servir como ponto único de manutenção quando as listas mudarem.

Observação:
    - Os valores aqui são apenas exemplos. O usuário pode ajustá-los na
      interface sem alterar o código.
    - Não há dados pessoais nem credenciais neste módulo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# UFs do Brasil (código de duas letras)
# ---------------------------------------------------------------------------

UFS_BRASIL: list[str] = [
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA",
    "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN",
    "RS", "RO", "RR", "SC", "SP", "SE", "TO",
]


# ---------------------------------------------------------------------------
# Situações cadastrais (códigos oficiais da Receita Federal)
# ---------------------------------------------------------------------------

SITUACOES_CADASTRais: dict[str, str] = {
    "01": "Nula",
    "02": "Ativa",
    "03": "Suspensa",
    "04": "Inapta",
    "08": "Baixada",
}


# ---------------------------------------------------------------------------
# Município de exemplo (Goiânia-GO)
# ---------------------------------------------------------------------------

# Código do município na tabela oficial da Receita Federal.
# Este valor é apenas um exemplo inicial; o usuário pode alterá-lo.
MUNICIPIO_EXEMPLO: str = "5208707"


# ---------------------------------------------------------------------------
# CNAEs de exemplo
# ---------------------------------------------------------------------------

CNAES_EXEMPLO: list[str] = [
    "4637-1/99",   # Comércio atacadista de produtos alimentícios
    "4632-0/02",   # Comércio atacadista de aves abatidas
    "4633-8/01",   # Comércio atacadista de leite e laticínios
    "4634-6/01",   # Comércio atacadista de cereais e leguminosas
    "4635-4/02",   # Comércio atacadista de bebidas com atividade de fracionamento
    "4636-2/02",   # Comércio atacadista de mercadorias em geral
    "4639-7/01",   # Comércio atacadista de produtos alimentícios em geral
    "4691-5/00",   # Comércio atacadista de mercadorias em geral (inter)
]


# ---------------------------------------------------------------------------
# Palavras-chave de classificação (nome fantasia)
# ---------------------------------------------------------------------------

# A ordem das categorias define a precedência: a primeira que casar vence.
# O usuário pode reordenar via interface, mas a ordem padrão é esta.
PALAVRAS_CHAVE_CLASSIFICACAO: dict[str, list[str]] = {
    "Distribuidora": [
        "distribuidora", "distribuidor", "distribuição", "distribuicao",
    ],
    "Atacadista": [
        "atacadista", "atacado", "atacarejo",
    ],
    "Empório": [
        "empório", "emporio",
    ],
    "Representação comercial": [
        "representação", "representacoes", "representações",
        "representante", "representacoes comerciais",
    ],
    "Armazém": [
        "armazém", "armazem", "armazenagem",
    ],
    "Depósito": [
        "depósito", "deposito", "depósitos",
    ],
    "Suprimentos": [
        "suprimentos", "suprimento",
    ],
    "Outros": [],  # categoría final, sempre atribuída se nada casar
}


# ---------------------------------------------------------------------------
# Palavras-chave de exemplo usadas na interface
# ---------------------------------------------------------------------------

PALAVRAS_CHAVE_INCLUSAO_EXEMPLO: list[str] = [
    "distribuidora",
    "atacadista",
    "alimentos",
]

PALAVRAS_CHAVE_EXCLUSAO_EXEMPLO: list[str] = [
    "inativa",
    "baixada",
]


# ---------------------------------------------------------------------------
# Estrutura de exemplo de configuração de filtros
# ---------------------------------------------------------------------------

@dataclass
class FiltrosExemplo:
    """Agrupa um exemplo de configuração de filtros.

    Útil para documentação e para testes rápidos.
    """

    uf: Optional[str] = "GO"
    municipio_codigo: Optional[str] = MUNICIPIO_EXEMPLO
    situacoes: Optional[list[str]] = field(default_factory=lambda: ["02"])
    cnaes_interesse: Optional[list[str]] = field(
        default_factory=lambda: list(CNAES_EXEMPLO[:3])
    )
    palavras_chave_incluir: Optional[list[str]] = field(
        default_factory=lambda: list(PALAVRAS_CHAVE_INCLUSAO_EXEMPLO)
    )
    palavras_chave_excluir: Optional[list[str]] = field(
        default_factory=lambda: list(PALAVRAS_CHAVE_EXCLUSAO_EXEMPLO)
    )
    exigir_telefone: bool = False
    exigir_email: bool = False
    combinacao: str = "AND"


FILTROS_EXEMPLO = FiltrosExemplo()