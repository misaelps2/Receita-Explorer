# Receita Explorer

Aplicação web local (Streamlit) para importar, filtrar, classificar e exportar
dados públicos de estabelecimentos empresariais da Receita Federal do Brasil.

## Descrição

O Receita Explorer permite que analistas de dados, desenvolvedores e demais
interessados processem o arquivo oficial de **Estabelecimentos** da Receita
Federal (layout público), apliquem filtros configuráveis (UF, município,
situação cadastral, CNAE, palavras-chave, presença de telefone/e-mail etc.) e
exportem o resultado em CSV, XLSX, TXT e JSON.

O processamento é feito **em blocos** com Pandas, de modo que arquivos grandes
não precisam ser carregados integralmente na memória.

## Problema que o projeto resolve

Os arquivos nacionais de estabelecimentos da Receita Federal são volumosos e
possuem um layout específico, delimitado por `;`, com campos que exigem
cuidados (zeros à esquerda em CNPJ, CEP, telefone; datas no formato
`AAAAMMDD`; múltiplos CNAEs secundários). Filtrar e organizar esses dados com
planilhas comuns é inviável. Este projeto fornece uma interface local simples,
testável e auditável para essa tarefa.

## Funcionalidades

- Seleção de competência (ex.: `2026-10`).
- Importação de arquivo local já baixado.
- Tentativa de download automático a partir da página de compartilhamento,
  quando um link direto puder ser identificado com segurança.
- Processamento em blocos (tamanho configurável).
- Filtros combináveis (AND/OR) por:
  - UF
  - Código do município (tabela oficial)
  - Situação cadastral
  - CNAE principal
  - Lista de CNAEs de interesse (principal + secundários)
  - Palavras-chave incluídas / excluídas
  - Presença de telefone
  - Presença de e-mail
  - Período de início de atividade
  - Nome fantasia
  - CNPJ
- Classificação por categorias (Distribuidora, Empório, Atacadista, etc.).
- Normalização e validação de CNPJ, telefone, e-mail, datas e endereços.
- Remoção de duplicados pelo CNPJ completo.
- Tabela de resultados pesquisável no Streamlit.
- Exportação para CSV (`;`, UTF-8 com BOM), XLSX, TXT e JSON.
- Logging com `logging` (sem dados pessoais sensíveis nos logs).
- Testes automatizados com `pytest` (independentes de rede).
- GitHub Actions executando os testes.

## Tecnologias

- Python 3.10+
- Streamlit
- Pandas
- Requests
- OpenPyXL
- Pytest




# 1. Clonar e entrar no projeto
git clone <url-do-repositorio> receita-explorer
cd receita-explorer

# 2. Criar e ativar ambiente virtual
python3 -m venv .venv
source .venv/bin/activate

# 3. Atualizar pip e instalar dependências
pip install --upgrade pip
pip install -r requirements.txt

# 4. Executar a aplicação
streamlit run app.py


