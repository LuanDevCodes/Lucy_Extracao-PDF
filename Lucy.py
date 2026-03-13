# Projeto Lucy - Extração de informação de relatórios PDF e criação de JSON

# Bibliotecas usadas no projeto
import time # Para algumas funções que utilizam horário, é do próprio python
import os # Para poder conversar com o SO
import json # Precisa dela para a geração dos arquivos JSON que serão o log do projeto
import re # Vem de Regex, é especialista em padões, não procura palavras em si. É muito importante para capturar datas e números
import camelot # Especializada em extrair informações de PDF's em coordenadas espaciais (x e Y), uso em conjunto com a pypdf
import requests # Necessária para a comunicação direta com a API
from pypdf import PdfReader # Para trabalharmos com os PDF's, descobri ao longo de testes que ela n é boa com tabelas
from datetime import datetime, timedelta # O timedelta é para fazer as contas usando as horas, é bem útil
from pathlib import Path # Usada quando precisamos navegar por pastas de arquivos
from dotenv import load_dotenv # Para carregar o arquivo .env, com ele eu consigo trancar tudo e deixar o repositório público :D

# --------------------------------------------------------------------------------------------------------------------
# ORGANIZANDO AS VARIÁVEIS GLOBAIS
# --------------------------------------------------------------------------------------------------------------------
# Carrega as variáveis do arquivo .env
load_dotenv()

# Criando as variáveis para as pastas, deixo tudo no dotenv tbm
pasta_pdf = os.getenv("PASTA_PDF")
pasta_json = os.getenv("PASTA_JSON")
url_api = os.getenv("URL_API")

# Data de corte: ela só processará arquivos modificados após esta data, separei no formato Br pra ficar mais fácil e legível
d = int(os.getenv("DIA_CORTE"))
m = int(os.getenv("MES_CORTE"))
a = int(os.getenv("ANO_CORTE"))

# invertendo internamente para o padrão do Python, deixei assim por gosto pessoal, mas não é algo crucial ao projeto
data_corte = datetime(a, m, d)

# --------------------------------------------------------------------------------------------------------------------
# ORGANIZANDO AS FUNÇÕES PRINCIPAIS DO PROJETO
# --------------------------------------------------------------------------------------------------------------------

# O código é dividido por funções especializadas, cada uma responsável por uma parte

# ----------------------------------------------------------

# Função responsável por extrair todo o texto do PDF
def extrair_texto_do_pdf(caminho_arquivo):
    try:
        reader = PdfReader(caminho_arquivo)
        texto_completo = ""
        for pagina in reader.pages:
            texto_completo = texto_completo + pagina.extract_text()
        return texto_completo
    except Exception as e:
        print(f"❌ Erro ao ler o arquivo {caminho_arquivo}: {e}")
        return None

# -------------------------------
# *******************************
# -------------------------------

# Função responsável por utilizar o camelot para a extração dos dados da tabela, com o pypdf isso é muito complicado
def extrair_tabela_com_camelot(caminho_arquivo, reidi_prioritario):
    itens_pedido = []
    
    try:
        # Definimos onde cada coluna 'nasce' no eixo X (da esquerda para a direita)
        # Exemplo: Item começa em 50, Req em 80, Data em 120...
        minhas_colunas = '60, 100, 150, 230, 280, 380, 420, 460, 520' 

        tabelas = camelot.read_pdf(
            caminho_arquivo, 
            pages='1', # Isso é válido na coleta da tabela, ou seja, usaremos apenas a primeira página na coleta da tabela
            flavor='stream',
            columns=[minhas_colunas] # Forçamos as divisões aqui!
        )
        
        if tabelas.n > 0:
            
            # Pegamos a primeira tabela detectada
            df = tabelas[0].df 
            
            # Vamos localizar a linha que contém o cabeçalho real
            idx_cabecalho = -1
            for i, linha in df.iterrows():
                linha_str = " ".join(linha.astype(str)).upper()
                if "ITEM" in linha_str and "DESCRIÇÃO" in linha_str:
                    idx_cabecalho = i
                    break
            
            if idx_cabecalho != -1:
                
                # Removemos tudo o que vem antes do cabeçalho, é bom para evitar capturas erradas
                df_dados = df.iloc[idx_cabecalho + 1:]
                
                # Mapeamos as colunas baseadas na linha do cabeçalho
                colunas = df.iloc[idx_cabecalho].tolist()
                
                # -------------------------------
                # **********SUB-FUNÇÃO***********
                # -------------------------------
                
                # Sub-função para buscar as colunas corretas pelo nome, isso é preciso pq elas podem mudar de posição
                def buscar_col(termos):
                    for i, c in enumerate(colunas):
                        if any(t.upper() in str(c).upper() for t in termos): return i
                    return -1

                coluna_item = buscar_col(["ITEM"])
                coluna_data = buscar_col(["DATA", "REMESSA"])
                coluna_proj = buscar_col(["DESCRIÇÃO", "PRODUTO"])
                coluna_valor = buscar_col(["TOTAL"])
                coluna_reidi = buscar_col(["REIDI"])

                for _, linha in df_dados.iterrows():
                    
                    # Limpeza e Captura Básica
                    v_item = str(linha[coluna_item]).strip() if coluna_item != -1 else ""
                    
                    # Itens de pedido costumam ser 00010, 00020... 
                    # Se vier "UA", "TOTAL" ou vazio, a Lucy descarta na hora
                    if not v_item.isdigit():
                        continue
                    
                    # Convertendo o valor do Item para um valor Int para poder ser lido pela API, verifica novamente se é digito
                    v_item_int = int(v_item) if v_item.isdigit() else 0
                    
                    # Capturando o RAIDI usando a lógica de verificação de dois fatores
                    # Pegamos a opinião da tabela (Trava de segurança)
                    reidi_tabela = "NÃO"
                    if coluna_reidi != -1:
                        conteudo = str(linha[coluna_reidi]).strip().upper()
                        
                        # só é SIM se estiver escrito SIM ou tiver um 'X'
                        if conteudo in ["SIM", "X", "S"]:
                            reidi_tabela = "SIM"
                    
                    # Se achamos a informação clara no texto (reidi_prioritario), usamos ela, senão, confiamos na tabela
                    # Basicamente verifica se ele existe, ou se recebemos algo, 
                    # nesse caso é a mesma coisa que validar se ela chegou mesmo
                    if reidi_prioritario:
                        v_reidi = reidi_prioritario
                        print("🧐 Peguei a informação de REIDI do texto")
                    else:
                        v_reidi = reidi_tabela # Se ela não chegou então a gente confia na da tabela mesmo
                        print("🚩 Não encontrei a informação de REIDI no texto, recorrendo a da tabela")
                    
                    # Captura bruta da data de remessa
                    v_data_re_bruta = str(linha[coluna_data]).strip() if coluna_data != -1 else ""
                    
                    # limpeza na data da remessa também
                    # Remove pontos, barras ou traços para padronizar e depois inverte
                    v_data_re_limpa = v_data_re_bruta.replace(".", "/") # Garante que tudo vire barra primeiro
                    
                    # Invertendo a data de remessa para o formato que é aceito no DB
                    if "/" in v_data_re_limpa:
                        dia, mes, ano = v_data_re_limpa.split("/")
                        data_remessa_db = f"{ano}-{mes}-{dia}" # Formato DB: YYYY-MM-DD
                    else:
                        data_remessa_db = v_data_re_limpa # Fallback caso falhe, voltando pra versão anterior as mudanças
                      
                    # Buscando pela descrição utilizando uma sub-função
                    def obter_desc_real(linha_atual, coluna_base):
                        
                        # Candidatos: a coluna alvo, a anterior e a próxima
                        indices_para_testar = [coluna_base, coluna_base - 1, coluna_base + 1]
                        
                        for idx in indices_para_testar:
                            
                            # Pula se o índice for inválido para esta linha
                            if idx < 0 or idx >= len(linha_atual):
                                continue
                                
                            texto = str(linha_atual[idx]).replace("\n", " ").strip()
                            
                            # Só aceitamos se NÃO for "UA", NÃO for só número e tiver tamanho
                            if texto and not texto.upper().startswith("UA") and not texto.isdigit() and len(texto) > 3:
                                return texto
                        return "Descrição não localizada"

                    # Aplicando a busca
                    v_proj_bruto = obter_desc_real(linha, coluna_proj)

                    # Lógica do Traço, com ela conseguimos separar a descrição e pegar apenas o número
                    partes = v_proj_bruto.split("-", 1)
                    if len(partes) > 1 and any(c.isdigit() for c in partes[0]):
                        projeto_final = partes[0].strip()
                    else:
                        projeto_final = v_proj_bruto

                    # Limpeza final de resquícios de "UA" que possam ter grudado, é importante pq os dados estavam misturando
                    projeto_final = re.sub(r"\s+UA\s+\d+", "", projeto_final, flags=re.IGNORECASE).strip()
                    
                    # Dentro do loop da extrair_tabela_com_camelot
                    v_valor_bruto = str(linha[coluna_valor]).strip() if coluna_valor != -1 else "0,00"

                    # Limpeza para virar número: remove ponto de milhar e troca vírgula decimal por ponto
                    v_valor_limpo = v_valor_bruto.replace(".", "").replace(",", ".")

                    # IS_REIDI é uma variável booleana (True/False), é uma convenção entre programadores experientes usar o is_
                    # pra indicar que a variável guarda um valor booleano
                    if v_reidi == "SIM":
                        is_reidi = True   # Atribui o valor Booleano Verdadeiro
                    else:
                        is_reidi = False  # Atribui o valor Booleano Falso

                    itens_pedido.append({
                        "item": v_item_int,
                        "data_remessa": data_remessa_db,
                        "projeto": projeto_final,
                        "valor_total": v_valor_limpo,
                        "reidi": is_reidi 
                    })
                                                
    except Exception as e:
        print(f"⚠️ Erro no Camelot: {e}")
        
    return itens_pedido

# -------------------------------
# *******************************
# -------------------------------

# Função revisada para processar o cabeçalho e chamar o Camelot para a tabela
def processar_informacoes(texto_bruto, caminho_arquivo):
    
    # Razão Social: Geralmente a primeira linha, pegamos o texto que vem antes de "Dados de Faturamento"
    match_razao = re.search(r"^(.*?)(?=\nDados de Faturamento)", texto_bruto, re.DOTALL | re.MULTILINE)
    v_razao = match_razao.group(1).strip() if match_razao else "Razão Social não encontrada"
    
    # Endereço: Capturamos o bloco e fatiamos depois
    match_end_completo = re.search(r"Dados de Faturamento\s+(.+?)(?=\s*CNPJ:)", texto_bruto, re.DOTALL)
    end_bruto = match_end_completo.group(1).replace("\n", " ").strip() if match_end_completo else ""
    
   # Fazendo uma limpeza e separação no endereço
    logradouro, numero_end, cep = "Não encontrado", "S/N", "00000-000"
    
    if end_bruto:
        
        # Pega o CEP primeiro (ele é o âncora)
        m_cep = re.search(r"\d{5}-\d{3}", end_bruto)
        if m_cep: 
            cep = m_cep.group()
            
            # Removemos o CEP da string para ele não atrapalhar a busca do número da casa
            end_sem_cep = end_bruto.replace(cep, "").strip()
        
        # Busca o número (sequência de dígitos que pode ter . ou -)
        # Procuramos o número que costuma vir após o nome da rua
        m_num = re.search(r"\s(\d+[\d.-]*)\b", end_sem_cep)
        if m_num:
            numero_end = m_num.group(1)
            
            # Logradouro é tudo o que vem antes do número
            pos_num = m_num.start()
            logradouro = end_sem_cep[:pos_num].strip()
            
    # Captura de Campos Simples (Regex)
    
    # Pegando o N° do PR
    match_pr = re.search(r"Nº do PR:\s*(.+)", texto_bruto)
    v_pr = match_pr.group(1).strip() if match_pr else "Não encontrado"

    # Pegando a Data
    match_data = re.search(r"Data:\s*(\d{2})[./](\d{2})[./](\d{4})", texto_bruto)
    data_pedido_db = f"{match_data.group(3)}-{match_data.group(2)}-{match_data.group(1)}" if match_data else "Não encontrado"

    # Pegando o CNPJ
    match_cnpj = re.search(r"CNPJ:\s*([\d\./-]+)", texto_bruto)
    v_cnpj = match_cnpj.group(1) if match_cnpj else "Não encontrado"

    # Pegando o IE
    match_ie = re.search(r"IE:\s*([\d.]+)", texto_bruto)
    v_ie = match_ie.group(1) if match_ie else "Não encontrado"
    
    # O Regex busca: número + parênteses + REIDI: + SIM ou NÃO, essa é a prioridade em cima da tabela, uma trava de segurança
    # Ex: 4)REIDI: NÃO ou 1) REIDI: SIM
    match_reidi_global = re.search(r"\d+\)\s*REIDI:\s*(SIM|NÃO)", texto_bruto, re.IGNORECASE)
    reidi_prioritario = match_reidi_global.group(1).upper() if match_reidi_global else None
    
    # Passandos ela para a outra função conseguir utilizar, extração da tabela feita pelo Camelot e atribuição a uma variável
    itens_pedido = extrair_tabela_com_camelot(caminho_arquivo, reidi_prioritario)

    # Coletando as informações adicionais via Camelot
    contrato_final = "Não encontrado"
    v_regiao = "Não encontrada"

    try:
        todas_as_tabelas = camelot.read_pdf(caminho_arquivo, pages='1', flavor='stream')
        
        if todas_as_tabelas.n > 0:
            df_rodape = todas_as_tabelas[-1].df
            linha_regiao = -1
            
            # Localiza o simbolo # (Procura a âncora), com ele fica muito mais fácil se guiar e limitar a área de busca
            # A variável de região, apesar de ser coletada não é passada para API ou JSON, é mais para localização no texto
            for l in range(len(df_rodape)):
                for c in range(len(df_rodape.columns)):
                    celula = str(df_rodape.iloc[l, c])
                    if "#" in celula:
                        linha_regiao = l
                        v_regiao = celula.split("#")[-1].strip()
                        v_regiao = re.split(r"\s{2,}", v_regiao)[0].strip()
                        break
                if linha_regiao != -1: break

            # Processando o contrato, por isso a importância do # acima, me guio com ele para achar as outras informações
            if linha_regiao != -1:
                
                # Pegamos o texto das linhas próximas (3 acima e 2 abaixo)
                linhas_alvo = range(max(0, linha_regiao - 3), min(len(df_rodape), linha_regiao + 2))
                
                texto_linha = ""
                for l in linhas_alvo:
                    texto_linha += " " + " ".join(df_rodape.iloc[l].astype(str))
                
                texto_linha = re.sub(r"\s+", " ", texto_linha).upper()
                pos_projeto = texto_linha.find("PROJETO")
                nums_encontrados = list(re.finditer(r"\b\d{8,12}\b", texto_linha))
                
                codigo_tabela = itens_pedido[0]['projeto'] if itens_pedido else ""
                
                for match in nums_encontrados:
                    num = match.group()
                    pos_num = match.start()
                    
                    # Filtros de Exclusão
                    if num == v_pr or num in codigo_tabela:
                        continue
                    
                    # Se o número vem depois da palavra PROJETO, ignoramos, pq ai não será o contrato mas outro número no meio
                    if pos_projeto != -1 and pos_num > pos_projeto:
                        continue
                    
                    # Se chegou aqui, é o Contrato de fato e podemos pegar ele
                    contrato_final = num
                    break 

            print(f"\n--- DEBUG LUCY ---")
            print(f"📃 Contrato Identificado: {contrato_final}")

    except Exception as e:
        print(f"⚠️  Erro ao processar vizinhança: {e}")

    # Montagem final do Json, juntando tudo numa lista com dicionários
    dados_finais = {
        "cabecalho": {
            "razao_social": v_razao,
            "numero_pr": v_pr,
            "data": data_pedido_db,
            "cnpj": v_cnpj,
            "ie": v_ie  
        },
        "endereco": [
            {
                "logradouro": logradouro,
                "numero_endereco": numero_end,
                "bairro": "",
                "cep": cep
            }
        ],
        "itens_pedido": itens_pedido, # Passando a variável que guarda o resultado da função que usa o Camelot nas tabelas
        "informacoes": {
            "contrato": contrato_final,
            
            # Para o caminho eu pego ele dos parâmetros da função, o normapath padroniza o caminho para o SO
            # a abspath garante o caminho completo, uma nota importante é que no JSON as barras virão duplicadas mas
            # ao serem enviadas para API elas estarão normais, o python coloca as barras para dizer que não é um comando especial
            "caminho_pdf": os.path.normpath(os.path.abspath(caminho_arquivo))
        }
    }
    
    return dados_finais

# -------------------------------
# *******************************
# -------------------------------

# Função responsável por entrar em contato com  API e passar os parâmetros para a inclusão do DB
def comunicar_API(dados_json):
    
    if not url_api:
        print("⚠️ Erro: URL da API não configurada no .env")
        return False

    try:
        # Enviamos o json via POST
        # timeout=15 significa que se a API não responder em 15s, a Lucy desiste e segue o baile
        
        # Estamos passando o dado do JSON montado para API
        resposta = requests.post(url_api, json=dados_json, timeout=15)

        # O 'ok' é um meio de saber se deu certo o envio para a API, poderia ser [200, 201] tbm
        if resposta.ok:
            print(f"🌐 Dados enviados para a API com sucesso - (Status: {resposta.status_code})")
            return True
        else:
            print(f"❌ Falha no envio para a API - Erro: {resposta.status_code}")
            print(f"🔍 Detalhes do servidor: {resposta.text}") # Ajuda muito no debug
            return False

    except requests.exceptions.RequestException as e:
        
        # Captura erros de rede (ex: cabo desconectado, servidor offline)
        print(f"📡 Erro de conexão com a API: {e}")
        return False

# -------------------------------
# *******************************
# -------------------------------

# Função responsável por pegar a hora atual do sistema, vai ajudar nas exibições, pega somente as horas e os minutos
def get_hora_atual() -> str:
    return datetime.now().strftime("%H:%M")

# --------------------------------------------------------------------------------------------------------------------
# A FUNÇÃO MAIN PRINCIPAL DO PROJETO, RESPONSÁVEL POR CHAMAR AS OUTRAS E CONDUZIR TUDO
# --------------------------------------------------------------------------------------------------------------------

# O corpo do projeto, vai ser responsável por iniciar as funções, a primeiro momento é um loop while infinito, mas pode mudar
# Dependendo dos próximos passos do projeto
def main():
    print(f"\n🪆  Lucy iniciando seus serviços - {get_hora_atual()}")
    print(f"📅 Filtro ativo: Processando arquivos modificados após {data_corte.strftime('%d/%m/%Y')}\n")
    
    # Caminho do arquivo que servirá de memória para a Lucy
    arquivo_memoria = Path(pasta_json) / "pdfs_processados.log"
    
    # Caso o arquivo de log não exista a primeiro momento, ele é criado, se ele existir ele apenas atualiza a data de acesso
    # mas não chega a apagar nada
    if not arquivo_memoria.exists():
        arquivo_memoria.touch() # O comando .touch() cria o arquivo em branco, vem do Linux :D
        print(f"📁 Arquivo de log criado em: {arquivo_memoria}")
        
    busca_arquivos = True # É a variável para controle do aviso de arquivos encontrados
    
    while True:
        try:
            if not os.path.exists(pasta_pdf):
                print(f"⚠️ Pasta de PDF não encontrada: {pasta_pdf}")
                time.sleep(10)
                continue
            
            # Carregando a memória do arquivo para não reprocessar
            with open(arquivo_memoria, "r") as f:
                processados = set(f.read().splitlines())

            arquivos = os.listdir(pasta_pdf)
            existem_arquivo= False # Variável para controle de arquivos atuais, com isso saberemos se ela não leu nenhum
            
            for nome_arquivo in arquivos:
                
                if not nome_arquivo.endswith('.pdf') or nome_arquivo in processados:
                    continue
                
                caminho_completo = os.path.join(pasta_pdf, nome_arquivo)
                
                # Pega a data de modificação do arquivo no Windows
                mtime = os.path.getmtime(caminho_completo)
                data_modificacao = datetime.fromtimestamp(mtime)

                if data_modificacao < data_corte:
                    # Se for antigo, ignoramos silenciosamente conforme especificado na definição da data de corte
                    continue
                
                # Condicional para processamento dos arquivos válidos
                if data_modificacao >= data_corte:
                    existem_arquivo = True # Se a data de modificação for maior ou igual a de corte, então ele existe e é válido
                
                    print("-" * 70)
                    print(f"📍 Detectado: {nome_arquivo}")

                    texto_pdf = extrair_texto_do_pdf(caminho_completo)
                    
                    if texto_pdf:
                        
                        # Importante lembrar que a processar_informacoes já invoca a que extrai dados da tabela via Camelot
                        dados_extraidos = processar_informacoes(texto_pdf, caminho_completo)
                        
                        # Chamando a API e passando os parâmetros coletados e com tudo montado
                        # Aqui vamos verificar se deu certo a comunicação com a API, se for True seguimos e senão ela nem continua
                        # usar um IF assim basicamente verifica "IF tal coisa True", ele chama a função e pega o resultado
                        if comunicar_API(dados_extraidos):
                        
                                # Lógica para o nome do arquivo JSON: PR + Data (limpa para o formato que o Windows aceita)
                                pr_limpo = dados_extraidos["cabecalho"]["numero_pr"].replace("/", "-")
                                data_limpa = dados_extraidos["cabecalho"]["data"].replace("/", "-")
                                
                                # Caso por alguma razão ele não consiga o PR, ele deixa o nome original para não travar quando salvar
                                pr_valido = pr_limpo if "Não" not in pr_limpo else nome_arquivo.replace(".pdf", "")
                                nome_json = f"PR_{pr_valido}_{data_limpa}.json"
                                
                                caminho_salvamento = Path(pasta_json) / nome_json
                                os.makedirs(pasta_json, exist_ok=True)
                                
                                with open(caminho_salvamento, 'w', encoding='utf-8') as f:
                                    json.dump(dados_extraidos, f, ensure_ascii=False, indent=4)
                                
                                # Registrando na memória para nunca mais ler este arquivo
                                # Nota importante, caso não exista o arquivo (numa primeira vez rodando por exemplo), ele cria ele por causa
                                # do "a" de append, criei uma condicional lá em cima pois ele seria capaz de seguir o fluxo sem travar
                                with open(arquivo_memoria, "a") as f:
                                    f.write(nome_arquivo + "\n")
                                
                                print(f"📸 '{nome_arquivo}' processado e registrado no log")
                                print(f"✅ Dados de {nome_arquivo} salvos como {nome_json}")
                                
                                print(f"\n🎉 '{nome_arquivo}' processado, enviado e registrado com sucesso")
                                print(("-" * 70 + "\n"))
                        else:
                            print(f"⏳ {nome_arquivo} não foi enviado. Ele ficará pendente para a próxima tentativa (Não salvo)")
            
            # Com essa lógica ele só vai imprimir se não tiver nada e for a primeira busca ou se na última ele encontrou algo
            if not existem_arquivo and busca_arquivos:
                print(f"🔕 Nenhum arquivo novo detectado após a data {data_corte.strftime('%d/%m/%Y')} - Aguardando novo arquivo na Pasta\n")
                busca_arquivos = False
            
            # Se novos arquivos forem encontrados o aviso é resetado para que possa avisar novamente
            if existem_arquivo:
                busca_arquivos = True

        except Exception as e:
            print(f"⚠️  Erro na vigilância: {e}")

        time.sleep(5)

# O 'if __name__' garante que o robô só comece a rodar se este arquivo for executado diretamente
# isso evita que o loop infinito da Lucy ligue sozinho caso as funções sejam importadas em outro arquivo
if __name__ == "__main__":
    main()