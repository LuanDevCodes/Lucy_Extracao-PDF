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
