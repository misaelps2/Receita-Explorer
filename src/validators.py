"""
Normalização e validação de campos do layout de estabelecimentos da RFB.

Responsabilidade:
    - Montar e validar CNPJ a partir dos três componentes oficiais.
    - Normalizar e formatar telefones brasileiros (DDD + número).
    - Normalizar endereços, CEP e datas.
    - Validar sintaticamente e-mails (sem confirmar existência da caixa).
    - Tratar valores ausentes sem convertê-los em textos como ``"nan"``.

Este módulo é puro (sem efeitos colaterais) para facilitar testes unitários.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# Caracteres considerados "vazios" após ``strip``.
_VALORES_VAZIOS: set[str] = {
    "",
    "nan",
    "none",
    "null",
    "na",
    "n/a",
    "-",
}

_REGEX_DIGITOS = re.compile(r"\D+")

# Regex sintática de e-mail (não confirma existência da caixa postal).
# Baseada em uma simplificação prática da RFC 5322.
_REGEX_EMAIL = re.compile(
    r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$"
)


# ---------------------------------------------------------------------------
# Utilitários básicos
# ---------------------------------------------------------------------------

def limpar_texto(valor: Any) -> Optional[str]:
    """Limpa um valor textual removendo espaços e tratando ausências.

    Args:
        valor: Valor de entrada (pode ser ``None``, ``float('nan')`` etc.).

    Returns:
        Texto limpo ou ``None`` quando o valor for considerado ausente.

    Observações:
        - Strings como ``"nan"``, ``"None"`` e ``"null"`` são tratadas como
          ausência, evitando que apareçam nas saídas como se fossem dados.
    """
    if valor is None:
        return None
    if isinstance(valor, float) and pd.isna(valor):
        return None
    texto = str(valor).strip()
    if texto.lower() in _VALORES_VAZIOS:
        return None
    return texto


def somente_digitos(valor: Any) -> str:
    """Remove tudo que não for dígito do valor.

    Args:
        valor: Valor de entrada.

    Returns:
        String contendo apenas dígitos (possivelmente vazia).
    """
    texto = limpar_texto(valor) or ""
    return _REGEX_DIGITOS.sub("", texto)


# ---------------------------------------------------------------------------
# CNPJ
# ---------------------------------------------------------------------------

def montar_cnpj(
    cnpj_basico: Any,
    cnpj_ordem: Any,
    cnpj_dv: Any,
) -> Optional[str]:
    """Monta o CNPJ completo (14 dígitos) a partir dos três campos oficiais.

    Args:
        cnpj_basico: 8 dígitos (raiz).
        cnpj_ordem: 4 dígitos (ordem do estabelecimento).
        cnpj_dv: 2 dígitos verificadores.

    Returns:
        CNPJ com 14 dígitos sem pontuação, ou ``None`` se algum componente
        estiver ausente ou se o total de dígitos for diferente de 14.

    Observações:
        - A função **não** valida os dígitos verificadores; use
          :func:`validar_cnpj` para isso.
        - Os zeros à esquerda são preservados porque operamos sobre strings.
    """
    partes = [
        somente_digitos(cnpj_basico),
        somente_digitos(cnpj_ordem),
        somente_digitos(cnpj_dv),
    ]
    if not all(partes):
        return None
    cnpj = "".join(partes)
    if len(cnpj) != 14:
        return None
    return cnpj


def formatar_cnpj(cnpj: Any) -> Optional[str]:
    """Formata um CNPJ de 14 dígitos no padrão ``00.000.000/0000-00``.

    Args:
        cnpj: CNPJ em qualquer formato (com ou sem máscara).

    Returns:
        CNPJ formatado ou ``None`` se não houver exatamente 14 dígitos.
    """
    digitos = somente_digitos(cnpj)
    if len(digitos) != 14:
        return None
    return (
        f"{digitos[0:2]}.{digitos[2:5]}.{digitos[5:8]}/"
        f"{digitos[8:12]}-{digitos[12:14]}"
    )


def _calcular_dv_cnpj(base: str) -> str:
    """Calcula um dígito verificador do CNPJ pelo módulo 11.

    Args:
        base: String de dígitos (12 ou 13) sobre a qual calcular o DV.

    Returns:
        Um caractere de ``"0"`` a ``"9"`` representando o DV.
    """
    pesos = (
        [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        if len(base) == 12
        else [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    )
    soma = sum(int(d) * p for d, p in zip(base, pesos))
    resto = soma % 11
    if resto < 2:
        return "0"
    return str(11 - resto)


def validar_cnpj(cnpj: Any) -> bool:
    """Valida a estrutura e os dígitos verificadores de um CNPJ.

    Args:
        cnpj: CNPJ em qualquer formato (com ou sem máscara).

    Returns:
        ``True`` se o CNPJ tem 14 dígitos e os DVs conferem; caso contrário
        ``False``.

    Observações:
        - CNPJs com todos os dígitos iguais (ex.: ``00000000000000``) são
          rejeitados por construção.
    """
    digitos = somente_digitos(cnpj)
    if len(digitos) != 14:
        return False
    if digitos == digitos[0] * 14:
        return False
    dv1 = _calcular_dv_cnpj(digitos[:12])
    dv2 = _calcular_dv_cnpj(digitos[:12] + dv1)
    return digitos[12] == dv1 and digitos[13] == dv2


# ---------------------------------------------------------------------------
# Telefone
# ---------------------------------------------------------------------------

def normalizar_telefone(ddd: Any, numero: Any) -> Optional[str]:
    """Normaliza DDD + número em uma string apenas com dígitos.

    Args:
        ddd: DDD (2 dígitos).
        numero: Número do telefone (8 ou 9 dígitos, pode conter máscara).

    Returns:
        String no formato ``DDDNUMERO`` sem separadores, ou ``None`` se
        algum componente estiver ausente ou inválido.

    Observações:
        - Aceitamos DDD com 2 dígitos e número com 8 ou 9 dígitos.
        - Números incompletos são descartados para não gerar links de
          WhatsApp inválidos.
    """
    ddd_limpo = somente_digitos(ddd)
    num_limpo = somente_digitos(numero)
    if len(ddd_limpo) != 2:
        return None
    if len(num_limpo) not in (8, 9):
        return None
    return f"{ddd_limpo}{num_limpo}"


def formatar_telefone(telefone: Any) -> Optional[str]:
    """Formata um telefone brasileiro no padrão ``(DD) NNNNN-NNNN``.

    Args:
        telefone: Telefone em qualquer formato (só dígitos ou mascarado).

    Returns:
        Telefone formatado, ou ``None`` se a quantidade de dígitos não for
        10 (fixo) ou 11 (celular).
    """
    digitos = somente_digitos(telefone)
    if len(digitos) == 10:
        return f"({digitos[:2]}) {digitos[2:6]}-{digitos[6:]}"
    if len(digitos) == 11:
        return f"({digitos[:2]}) {digitos[2:7]}-{digitos[7:]}"
    return None


# ---------------------------------------------------------------------------
# E-mail
# ---------------------------------------------------------------------------

def normalizar_email(valor: Any) -> Optional[str]:
    """Normaliza um e-mail (trim e minúsculas) sem validar sintaxe.

    Args:
        valor: Texto de entrada.

    Returns:
        E-mail em minúsculas ou ``None`` se vazio.
    """
    texto = limpar_texto(valor)
    if texto is None:
        return None
    return texto.lower()


def validar_email(valor: Any) -> bool:
    """Valida sintaticamente um e-mail.

    Args:
        valor: Texto de entrada.

    Returns:
        ``True`` se o e-mail tem formato plausível; caso contrário ``False``.

    Observações:
        - Esta é uma validação **sintática**. Não confirma que a caixa
          postal existe, está ativa ou aceita mensagens.
    """
    texto = normalizar_email(valor)
    if texto is None:
        return False
    return bool(_REGEX_EMAIL.match(texto))


# ---------------------------------------------------------------------------
# CEP e endereço
# ---------------------------------------------------------------------------

def normalizar_cep(valor: Any) -> Optional[str]:
    """Normaliza CEP preservando zeros à esquerda.

    Args:
        valor: CEP em qualquer formato.

    Returns:
        CEP com 8 dígitos sem máscara, ou ``None`` se inválido.
    """
    digitos = somente_digitos(valor)
    if len(digitos) != 8:
        return None
    return digitos


def formatar_cep(valor: Any) -> Optional[str]:
    """Formata um CEP no padrão ``00000-000``.

    Args:
        valor: CEP em qualquer formato.

    Returns:
        CEP formatado ou ``None`` se inválido.
    """
    digitos = normalizar_cep(valor)
    if digitos is None:
        return None
    return f"{digitos[:5]}-{digitos[5:]}"


def normalizar_endereco(valor: Any) -> Optional[str]:
    """Normaliza um campo textual de endereço.

    Args:
        valor: Texto de entrada.

    Returns:
        Texto com espaços colapsados e capitalização preservada, ou ``None``
        se vazio.

    Observações:
        - Não alteramos maiúsculas/minúsculas para não distorcer nomes de
          logradouros e bairros.
    """
    texto = limpar_texto(valor)
    if texto is None:
        return None
    return re.sub(r"\s+", " ", texto)


# ---------------------------------------------------------------------------
# Datas
# ---------------------------------------------------------------------------

def converter_data_rfb(valor: Any) -> Optional[date]:
    """Converte uma data no formato ``AAAAMMDD`` para :class:`datetime.date`.

    Args:
        valor: String ou número representando a data no formato RFB.

    Returns:
        Objeto :class:`datetime.date` ou ``None`` se inválido/ausente.

    Observações:
        - A RFB usa ``0`` ou string vazia para datas ausentes; ambos viram
          ``None``.
    """
    digitos = somente_digitos(valor)
    if len(digitos) != 8:
        return None
    try:
        return datetime.strptime(digitos, "%Y%m%d").date()
    except ValueError:
        return None


def formatar_data_br(valor: Any) -> Optional[str]:
    """Converte uma data RFB para o formato ``DD/MM/AAAA``.

    Args:
        valor: Data no formato RFB ou já em ``date``.

    Returns:
        Data em ``DD/MM/AAAA`` ou ``None``.
    """
    if isinstance(valor, date):
        return valor.strftime("%d/%m/%Y")
    convertida = converter_data_rfb(valor)
    if convertida is None:
        return None
    return convertida.strftime("%d/%m/%Y")