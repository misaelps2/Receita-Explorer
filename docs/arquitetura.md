# Arquitetura do Receita Explorer

## Visão geral

O projeto segue uma separação clara entre interface, lógica de negócio e
infraestrutura de apoio:

- `app.py` — interface Streamlit e coordenação do fluxo.
- `config/filtros.py` — valores padrão de CNAEs, palavras-chave e UFs.
- `src/downloader.py` — descoberta e download de arquivos oficiais.
- `src/reader.py` — leitura em blocos e enriquecimento do DataFrame.
- `src/filters.py` — configuração e aplicação de filtros; classificação.
- `src/validators.py` — normalização e validação de CNPJ, telefone, e-mail,
  CEP, datas e endereços.
- `src/exporters.py` — geração de CSV, XLSX, TXT e JSON.
- `src/logger.py` — configuração de logging.
- `tests/` — testes automatizados independentes de rede.
- `docs/` — documentação complementar.

## Fluxo de dados

```mermaid
flowchart TD
    A[Usuário] -->|Competência + filtros| B[app.py]
    B -->|Importar arquivo local| C[Importação manual]
    B -->|Tentar download| D[src/downloader.py]
    D -->|Falha ou ausência de link| E[Mensagem: baixar manualmente]
    C --> F[src/reader.py]
    F -->|Lê em blocos| G[src/reader.py: _enriquecer_bloco]
    G -->|Aplica filtros| H[src/filters.py]
    H -->|Acumula aprovados| I[ResultadoProcessamento]
    I -->|Remove duplicados| J[src/filters.py: remover_duplicados]
    J -->|Classifica por palavras-chave| K[src/filters.py: classificar_dataframe]
    K --> L[Tabela na interface]
    K --> M[src/exporters.py]
    M --> N[CSV / XLSX / TXT / JSON]