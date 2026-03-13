# 🪆 Projeto Lucy - Extração de Dados de Relatórios PDF

A **Lucy** é uma ferramenta de automação desenvolvida em Python para monitorar pastas, extrair informações de relatórios em formato PDF, converter esses dados em arquivos JSON estruturados (servem como log de registro) e realizar a comunicação com o banco de dados via API para inserção dos dados coletados

### 📝 Descrição do Funcionamento
O projeto realiza uma varredura contínua em diretórios específicos em busca de novos arquivos PDF. Através de uma lógica de filtros, o sistema identifica apenas documentos modificados após uma determinada "data de corte" definida pelo usuário via variáveis de ambiente

Para garantir a integridade do processo, a Lucy utiliza um sistema de **Memória Persistente (Log)**, que registra cada arquivo processado com sucesso em um arquivo físico (`.log`), impedindo que o mesmo documento seja lido repetidamente, mesmo após o sistema ou a máquina serem reiniciados

---

### 🛠️ Bibliotecas Utilizadas

* **`Camelot-py`**: Especialista em extrair informações de PDFs com tabelas complexas através de coordenadas espaciais (eixos X e Y)
* **`PyPDF (PdfReader)`**: Utilizada para a extração do texto bruto e leitura inicial do conteúdo das páginas
* **`Requests`**: Biblioteca responsável pela comunicação via protocolo HTTP, permitindo que a Lucy envie os dados extraídos para uma API interna
* **`Regex (re)`**: Ferramenta essencial para a identificação de padrões de texto, como datas, CNPJs e números de contrato
* **`Pathlib / OS`**: Utilizadas para a manipulação de caminhos de arquivos, navegação entre pastas e interação direta com o Sistema Operacional
* **`Python-dotenv`**: Gerencia a segurança do projeto, permitindo o uso de variáveis de ambiente (como caminhos de pastas e URLs) sem expô-las no código fonte

---

### 🔄 Ciclo de Processamento (Pipeline)

Para garantir a eficiência e a integridade dos dados, a Lucy segue um fluxo lógico rigoroso em cada ciclo:

1. **Monitoramento**: Varredura contínua do diretório configurado em busca de novos arquivos `.pdf`
2. **Validação de Corte**: Comparação da data de modificação do arquivo com a data de corte do sistema
3. **Consulta de Memória**: Verificação no arquivo de log para evitar reprocessamento, está ligado com o monitoramento dela, realizando a verificação mesmo que ela seja reiniciada
4. **Extração Híbrida**: 
    * Captura de texto bruto e metadados via `PyPDF`.
    * Extração de tabelas complexas via `Camelot` (análise de coordenadas espaciais)
5. **Normalização**: Tratamento de tipos de dados (Inteiros, Booleanos) e formatação de datas para o padrão ISO 8601 (`YYYY-MM-DD`), é importante para a comunicação com a API interna
6. **Entrega Garantida**: Realiza o envio via `POST` para a API. O registro local e o log de sucesso **só são efetivados** após a confirmação (Status 200/201) do servidor de destino

---

### ⚙️ Configuração do Ambiente (.env)
Este projeto utiliza variáveis de ambiente para segurança. Foi necessário criar um arquivo `.env` na raiz do projeto seguindo o modelo:

```env
# Caminhos de Diretórios
PASTA_PDF=C:/caminho/para/seus/pdfs
PASTA_JSON=C:/caminho/para/salvamento/json

# Integração com Banco de Dados
URL_API=http://sua-api-csharp.com/api/v1/pedidos

# Filtro de Data de Corte (No formato Brasileiro)
DIA_CORTE=01
MES_CORTE=03
ANO_CORTE=2026
```
---

Trabalhar nesse projeto de automação e em outros que tive a oportunidade de desenvolver foram muito importantes pra fixação de conteúdo e comnpreensão da capacidade do Python em extração, manipulação, padronização e envio de dados.

