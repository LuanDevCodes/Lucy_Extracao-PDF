# 🪆 Projeto Lucy - Extração de Dados de Relatórios PDF

A **Lucy** é uma ferramenta desenvolvida em Python para a extração automatizada de dados de relatórios em formato PDF. Originalmente surgiu como um serviço de monitoramento contínuo, ela agora é parte de um **módulo de infraestrutura** integrado via API, servindo como o motor de processamento para sistemas (C#/.NET).

## 🚀 Arquitetura e Evolução
Atualmente, a Lucy opera sob demanda (**On-Demand Execution**), funcionando como uma ferramenta invocada pelo sistema principal:

* **Invocação por Evento:** O sistema (C#) aciona o executável apenas quando necessário
* **Seleção Inteligente:** Identifica automaticamente o arquivo mais recente na pasta de origem para processamento imediato
* **Granularidade de Dados:** Processa o cabeçalho complexo e extrai cada item da tabela individualmente
* **Integração Híbrida:** Envia os dados processados para uma API REST e gera simultaneamente um backup local em JSON para auditoria e refatoramento

---

### 🛠️ Bibliotecas Utilizadas

* **`Camelot-py`**: Especialista em extrair informações de PDFs com tabelas complexas através de coordenadas espaciais (eixos X e Y)
* **`PyPDF (PdfReader)`**: Utilizada para a extração do texto bruto e leitura inicial do conteúdo das páginas
* **`Requests`**: Biblioteca responsável pela comunicação via protocolo HTTP, permitindo que a Lucy envie os dados extraídos para uma API interna
* **`Regex (re)`**: Ferramenta essencial para a identificação de padrões de texto, como datas, CNPJs e números de contrato
* **`Pathlib / OS`**: Utilizadas para a manipulação de caminhos de arquivos, navegação entre pastas e interação direta com o Sistema Operacional
* **`Python-dotenv`**: Gerencia a segurança do projeto, permitindo o uso de variáveis de ambiente (como caminhos de pastas e URLs) sem expô-las no código fonte

---

## 📋 Fluxo de Funcionamento
1.  **Trigger:** O usuário solicita o processamento via interface do sistema principal
2.  **Scan:** A Lucy varre o diretório e seleciona o PDF com o registro de modificação mais recente
3.  **Extraction:** O texto e as tabelas são processados; campos como Razão Social, CNPJ, Itens, Datas e Valores são mapeados via Regex e lógica de colunas
4.  **Delivery:** Cada item extraído é disparado individualmente para o endpoint da API
5.  **Logging:** Um arquivo JSON consolidado é gerado na pasta de destino, contendo o log completo da extração para conferência técnica

### Variáveis de Ambiente (.env)
* `PASTA_PDF`: Caminho dos relatórios de entrada
* `PASTA_JSON`: Destino dos backups e logs de processamento
* `URL_API`: Endpoint para integração dos dados

## 🛡️ Melhorias Implementadas
* **Alta Performance:** Migração para o modo de diretório único, reduzindo o tempo de carregamento inicial (antes compilada num executável (onefile via pyinstaller)
* **Resiliência:** Tratamento de erros por item, garantindo que falhas em linhas específicas da tabela não interrompam a extração do documento inteiro
* **Feedback Visual:** Resumos de console formatados com emojis para facilitar o monitoramento em tempo real via Standard Output (stdout)

---

Nota pessoal: Trabalhar nesse projeto de automação e em outros que tive a oportunidade de desenvolver foi muito importante pra fixação de conteúdo e compreensão da capacidade do Python em extração, manipulação, padronização e envio de dados.
