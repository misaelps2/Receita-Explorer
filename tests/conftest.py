"""
Configuração compartilhada dos testes (fixtures).

Responsabilidade:
    - Disponibilizar fixtures reutilizáveis e dados sintéticos.
    - Garantir que os testes não dependam de rede nem de dados reais.

Observações:
    - Nenhum dado pessoal real é usado aqui. Todos os CNPJs, telefones e
      e-mails são fictícios.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

# Permite importar ``src`` e ``config`` diretamente quando ``pytest`` é
# executado a partir da raiz do projeto.
RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))


@pytest.fixture()
def df_exemplo() -> pd.DataFrame:
    """DataFrame sintético enriquecido para testes de filtros.

    Returns:
        DataFrame com duas empresas fictícias.
    """
    return pd.DataFrame(
        {
            "CNPJ_BASICO": ["12345678", "87654321"],
            "CNPJ_ORDEM": ["0001", "0002"],
            "CNPJ_DV": ["95", "70"],
            "CNPJ": ["12345678000195", "87654321000270"],
            "CNPJ_FORMATADO": ["12.345.678/0001-95", "87.654.321/0002-70"],
            "MATRIZ_FILIAL": ["1", "2"],
            "TIPO_ESTABELECIMENTO": ["Matriz", "Filial"],
            "NOME_FANTASIA": ["Distribuidora Alfa Ltda", "Empório Beta"],
            "SITUACAO_CADASTRAL": ["02", "02"],
            "CNAE_PRINCIPAL": ["4637-1/99", "4711-3/02"],
            "CNAE_SECUNDARIOS": ["", "4637-1/99"],
            "UF": ["GO", "SP"],
            "MUNICIPIO": ["5208707", "3550308"],
            "DDD_1": ["62", "11"],
            "TELEFONE_1": ["999999999", "33334444"],
            "DDD_2": ["", ""],
            "TELEFONE_2": ["", ""],
            "TELEFONE_NORMALIZADO": ["62999999999", "1133334444"],
            "TELEFONE_FORMATADO": ["(62) 99999-9999", "(11) 3333-4444"],
            "EMAIL": ["contato@alfa.com.br", "beta@emporio.com.br"],
            "EMAIL_NORMALIZADO": ["contato@alfa.com.br", "beta@emporio.com.br"],
            "CEP": ["74000000", "01000000"],
            "CEP_NORMALIZADO": ["74000000", "01000000"],
            "DATA_INICIO_ATIVIDADE": ["20100101", "20150515"],
            "DATA_ABERTURA": [
                pd.Timestamp("2010-01-01").date(),
                pd.Timestamp("2015-05-15").date(),
            ],
        }
    )


@pytest.fixture()
def arquivo_sintetico(tmp_path: Path) -> Path:
    """Cria um arquivo delimitado por ``;`` com o layout oficial.

    Args:
        tmp_path: Diretório temporário fornecido pelo pytest.

    Returns:
        Caminho do arquivo sintético criado.

    Observações:
        - As linhas usam o layout de estabelecimentos; os valores são
          fictícios.
        - A coluna CNPJ_DV é preenchida com DVs válidos calculados na hora.
    """
    from src.validators import _calcular_dv_cnpj  # uso interno para teste

    base1 = "12345678" + "0001"
    dv1 = _calcular_dv_cnpj(base1)
    dv1_completo = dv1 + _calcular_dv_cnpj(base1 + dv1)

    base2 = "87654321" + "0002"
    dv2 = _calcular_dv_cnpj(base2)
    dv2_completo = dv2 + _calcular_dv_cnpj(base2 + dv2)

    linhas = [
        ";".join([
            "12345678", "0001", dv1_completo, "1", "Distribuidora Alfa Ltda",
            "02", "20100101", "00", "", "", "20100101", "4637-1/99", "",
            "RUA", "DAS FLORES", "100", "SALA 1", "CENTRO", "74000000",
            "GO", "5208707", "62", "999999999", "", "", "", "",
            "contato@alfa.com.br", "", "",
        ]),
        ";".join([
            "87654321", "0002", dv2_completo, "2", "Empório Beta",
            "02", "20150515", "00", "", "", "20150515", "4711-3/02",
            "4637-1/99", "AV", "PAULISTA", "1000", "", "BELA VISTA",
            "01000000", "SP", "3550308", "11", "33334444", "", "", "", "",
            "beta@emporio.com.br", "", "",
        ]),
    ]
    caminho = tmp_path / "estabelecos_sintetico.csv"
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return caminho