# Projeto Lucy - Extração de informação de relatórios PDF e criação de JSON

# Bibliotecas usadas no projeto
import os # Para poder conversar com o SO
import json # Precisa dela para a geração dos arquivos JSON que serão o log do projeto
import re # Vem de Regex, é especialista em padões, não procura palavras em si. É muito importante para capturar datas e números
import camelot # Especializada em extrair informações de PDF's em coordenadas espaciais (x e Y), uso em conjunto com a pypdf
import requests # Necessária para a comunicação direta com a API
from pypdf import PdfReader # Para trabalharmos com os PDF's, descobri ao longo de testes que ela n é boa com tabelas
from datetime import datetime # O datetime é necessário para situações aonde preciso da data e hora
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

# --------------------------------------------------------------------------------------------------------------------
# ORGANIZANDO AS FUNÇÕES PRINCIPAIS DO PROJETO
# --------------------------------------------------------------------------------------------------------------------

# O código é dividido por funções especializadas, cada uma responsável por uma parte

# -------------------------------
# *******************************
# -------------------------------

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
        minhas_colunas = '60, 100, 150, 230, 280, 380, 420, 460, 520'

        # TENTATIVA 1: Modo Automático Padrão 
        tabelas = camelot.read_pdf(caminho_arquivo, pages='1', flavor='stream')
        
        # TENTATIVA 2: edge_tol alto 
        if tabelas.n == 0:
            print("🔄 Tabela rebelde detectada. Aumentando sensibilidade (edge_tol=500)...")
            tabelas = camelot.read_pdf(caminho_arquivo, pages='1', flavor='stream', edge_tol=500)
        
        # TENTATIVA 3: Coordenadas fixas 
        if tabelas.n == 0:
            print("💡 Tentando extração final com coordenadas fixas...")
            tabelas = camelot.read_pdf(caminho_arquivo, pages='1', flavor='stream', columns=[minhas_colunas])

        if tabelas.n == 0:
            print("⚠️ Nenhuma tabela detectada em nenhum dos 3 modos")
            return itens_pedido

        for idx_tabela in range(tabelas.n):
            df = tabelas[idx_tabela].df
            
            print(f"\n📄 Processando tabela {idx_tabela + 1} de {tabelas.n}...")
            
            idx_cabecalho = -1
            for i, linha in df.iterrows():
                linha_str = " ".join(
                    str(c).replace("\n", " ") for c in linha
                ).upper()
                if "ITEM" in linha_str and ("DESCRI" in linha_str or "PRODUTO" in linha_str):
                    idx_cabecalho = i
                    print(f"✅ Cabeçalho encontrado na linha {i} (tabela {idx_tabela + 1})")
                    break

            if idx_cabecalho == -1:
                print(f"⏭️  Tabela {idx_tabela + 1} sem cabeçalho reconhecível, pulando...")
                continue  # vai para a próxima tabela

            linhas_extras = 0
            for offset in range(1, 4):
                idx_check = idx_cabecalho + offset
                if idx_check >= len(df):
                    break
                
                # Pega só a primeira sub-linha da célula 0 (antes do primeiro \n)
                primeira_celula = str(df.iloc[idx_check, 0]).split("\n")[0].strip()
                if not primeira_celula.isdigit():
                    linhas_extras += 1
                else:
                    break

            print(f"↕️  Linhas extras de cabeçalho detectadas: {linhas_extras}")

            # -------------------------------------------------------------------
            # monta colunas — expande \n de cada célula do bloco de cabeçalho
            # garante que os índices em colunas[] batem com os do DataFrame
            # -------------------------------------------------------------------
            num_colunas_df = df.shape[1]
            colunas = [""] * num_colunas_df  # inicializa com o tamanho real do DF

            for offset in range(linhas_extras + 1):
                for col_idx in range(num_colunas_df):
                    celula = str(df.iloc[idx_cabecalho + offset, col_idx]).replace("\n", " ").strip()
                    if celula:  # só sobrescreve se tiver conteúdo útil
                        colunas[col_idx] = colunas[col_idx] + " " + celula

            colunas = [c.strip() for c in colunas]
            print(f"📋 Colunas mapeadas: {colunas}")

            df_dados = df.iloc[idx_cabecalho + 1 + linhas_extras:]

            def buscar_col(termos):
                for i, c in enumerate(colunas):
                    if any(t.upper() in str(c).upper() for t in termos):
                        return i
                if "ITEM" in termos:
                    return 0
                return -1

            coluna_item  = buscar_col(["ITEM"])
            coluna_data  = buscar_col(["DATA", "REMESSA"])
            coluna_valor = buscar_col(["TOTAL"])
            coluna_reidi = buscar_col(["REIDI"])

            print(f"🗂️  Colunas: item={coluna_item} | data={coluna_data} | valor={coluna_valor} | reidi={coluna_reidi}")

            # -------------------------------------------------------------------
            # LOOP DE ITENS
            # col 0 tem item+data juntos por \n — extraímos por sub-linha
            # -------------------------------------------------------------------
            for _, linha in df_dados.iterrows():

                celula_col0 = str(linha[0])
                sublinhas   = [s.strip() for s in celula_col0.split("\n") if s.strip()]

                # Sub-linha 0 da col 0 = número do item (ex: "00010")
                v_item = sublinhas[0] if sublinhas else ""

                if not v_item.isdigit():
                    continue

                v_item_int = int(v_item)

                # -------------------------------------------------------------------
                # data de remessa está na sub-linha 1 da col 0
                # mas só se coluna_data apontar para col 0
                # -------------------------------------------------------------------
                if coluna_data == 0:
                    
                    # Procura qualquer sub-linha que pareça uma data (dd.mm.aaaa ou dd/mm/aaaa)
                    data_encontrada = ""
                    for sublinha in sublinhas:
                        if re.search(r"\d{2}[./]\d{2}[./]\d{4}", sublinha):
                            data_encontrada = sublinha.strip()
                            break
                    v_data_re_bruta = data_encontrada
                else:
                    v_data_re_bruta = str(linha[coluna_data]).strip() if coluna_data != -1 else ""

                # Limpeza e inversão da data
                v_data_re_limpa = v_data_re_bruta.replace(".", "/")
                data_remessa_db = None
                if "/" in v_data_re_limpa:
                    partes_data = v_data_re_limpa.split("/")
                    if len(partes_data) == 3:
                        dia, mes, ano = partes_data
                        data_remessa_db = f"{ano}-{mes}-{dia}"

                # REIDI
                reidi_tabela = "NÃO"
                if coluna_reidi != -1:
                    conteudo = str(linha[coluna_reidi]).strip().upper()
                    if conteudo in ["SIM", "X", "S"]:
                        reidi_tabela = "SIM"

                if reidi_prioritario:
                    v_reidi = reidi_prioritario
                    print("🧐 Peguei a informação de REIDI do texto")
                else:
                    v_reidi = reidi_tabela
                    print("🚩 Não encontrei a informação de REIDI no texto, recorrendo a da tabela")

                # Valor total — sem alteração
                v_valor_bruto = str(linha[coluna_valor]).strip() if coluna_valor != -1 else "0,00"
                v_valor_bruto = v_valor_bruto.split("\n")[0].strip()  # pega só "Valor Total" real
                v_valor_limpo = v_valor_bruto.replace(".", "").replace(",", ".")

                is_reidi = v_reidi == "SIM"

                itens_pedido.append({
                    "item": v_item_int,
                    "data_remessa": data_remessa_db,
                    "valor_total": v_valor_limpo,
                    "reidi": is_reidi
                })

    except Exception as e:
        print(f"⚠️  Erro no Camelot: {e}")

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
    contrato_final = None # Para ir para o banco de dados como null preciso definir ela como None, o requests vai entender
    v_regiao = None

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
                    celulas = " ".join(
                        str(c).replace("\n", " ") for c in df_rodape.iloc[l]
                    )
                    texto_linha += " " + celulas

                texto_linha = re.sub(r"\s+", " ", texto_linha).upper()
                
                pos_projeto = texto_linha.find("PROJETO")
                nums_encontrados = list(re.finditer(r"\b\d{8,12}\b", texto_linha))
                
                for match in nums_encontrados:
                    num = match.group()
                    pos_num = match.start()
                    
                    # só descarta se for exatamente igual ao projeto ou ao PR
                    if num == v_pr:
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

    # Montagem final do Json, por causa da API é necessário fazer a montagem no modo payload plano
    dados_finais = {
            "razao_social": v_razao,
            "numero_pr": v_pr,
            "data": data_pedido_db,
            "cnpj": v_cnpj,
            "ie": v_ie,
            "endereco": end_bruto,
            "logradouro": logradouro,
            "numero_endereco": numero_end,
            "bairro": "",
            "cep": cep,
            "contrato": contrato_final,
            
            # Para o caminho eu pego ele dos parâmetros da função, o normapath padroniza o caminho para o SO
            # a abspath garante o caminho completo, uma nota importante é que no JSON as barras virão duplicadas mas
            # ao serem enviadas para API elas estarão normais, o python coloca as barras para dizer que não é um comando especial
            "caminho_pdf": os.path.normpath(os.path.abspath(caminho_arquivo))
    }
    
    # Estamos retornando os dados base e a lista de itens separadamente
    return dados_finais, itens_pedido

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
            
            try:
                os.makedirs(pasta_json, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                nome_log  = f"ERRO_API_{timestamp}_item{dados_json.get('item', 'X')}.json"
                caminho_log = os.path.join(pasta_json, nome_log)
                
                log_erro = {
                    "timestamp": timestamp,
                    "status_code": resposta.status_code,
                    "resposta_api": resposta.text,
                    "payload_enviado": dados_json  # aqui você vê exatamente o que foi mandado
                }
                
                with open(caminho_log, 'w', encoding='utf-8') as f:
                    json.dump(log_erro, f, ensure_ascii=False, indent=4)
                    
                print(f"📝 Log de erro salvo em: {nome_log}")
            except Exception as e_log:
                print(f"⚠️ Não foi possível salvar o log de erro: {e_log}")
            
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
# A FUNÇÃO MAIN DO PROJETO - AGORA ELA É RESPONSÁVEL POR REALIZAR A EXTRAÇÃO E ENVIAR PRO DB DIRETO
# --------------------------------------------------------------------------------------------------------------------

def main():
    print(f"\n🪆  Lucy iniciando seus serviços - {get_hora_atual()}")
    
    try:
        
        if not os.path.exists(pasta_pdf):
            print(f"⚠️  Pasta de PDF não encontrada: {pasta_pdf}")
            return 

        # Pegamos todos os arquivos .pdf da pasta
        arquivos = [os.path.join(pasta_pdf, f) for f in os.listdir(pasta_pdf) if f.endswith('.pdf')]
        
        if not arquivos:
            print("🔕 Nenhum arquivo PDF encontrado para processar")
            return

        # Ordenando os arquivos pela data de modificação e pegamos o último (o mais novo)
        arquivo_mais_recente = max(arquivos, key=os.path.getmtime)
        nome_arquivo = os.path.basename(arquivo_mais_recente)
        
        print("-" * 70)
        print(f"📍 Alvo identificado: {nome_arquivo}")

        texto_pdf = extrair_texto_do_pdf(arquivo_mais_recente)
        
        if texto_pdf:
            
            # Extração dos dados base e da lista completa de itens
            dados_base, lista_de_itens = processar_informacoes(texto_pdf, arquivo_mais_recente)
            
            print(f"📦 Extraídos {len(lista_de_itens)} itens da tabela. Iniciando registros...")

            itens_sucesso = 0
            
            # Registrando item por item
            # Aqui ela percorre a tabela e entrega cada linha individualmente
            for item_tabela in lista_de_itens:
                payload = dados_base.copy()
                payload.update(item_tabela)
                
                # Por enquanto mantemos o envio para a API que você já tem
                # Logo abaixo adicionaremos a função que insere direto no DB SQL
                if comunicar_API(payload):
                    itens_sucesso = itens_sucesso + 1
                else:
                    print(f"❌ Falha ao registrar item {item_tabela['item']}.")

            if itens_sucesso > 0:
                
                # Criando o nome do arquivo baseado no PR e Data
                pr_limpo = dados_base["numero_pr"].replace("/", "-")
                data_limpa = dados_base["data"].replace("/", "-")
                pr_valido = pr_limpo if "Não" not in pr_limpo else nome_arquivo.replace(".pdf", "")
                nome_json = f"PR_{pr_valido}_{data_limpa}.json"
                
                caminho_salvamento = Path(pasta_json) / nome_json
                
                # Se a pasta não existir é realizado a criação dela
                os.makedirs(pasta_json, exist_ok=True)
                
                with open(caminho_salvamento, 'w', encoding='utf-8') as f:
                    
                    # Criamos um log completo que junta os dados do cabeçalho com a lista de itens
                    log_local = dados_base.copy()
                    log_local["itens_completos"] = lista_de_itens
                    json.dump(log_local, f, ensure_ascii=False, indent=4)
                
                print(f"✅ Backup local salvo em: {nome_json} - {caminho_salvamento}")

            # Print final de resumo do arquivo (fora do loop dos itens), garante no nome de todos os itens da lista (tabela)
            if itens_sucesso == len(lista_de_itens):
                print(f"📸 Todos os {len(lista_de_itens)} itens de '{nome_arquivo}' foram registrados")
            else:
                print(f"⚠️  Atenção: Apenas {itens_sucesso}/{len(lista_de_itens)} itens foram registrados")
                
    except Exception as e:
        print(f"⚠️  Erro durante a extração: {e}")
        
    print(f"\n💤  Lucy encerrando suas atividades - {get_hora_atual()}")
    print("-" * 70 + "\n")

# O 'if __name__' garante que o robô só comece a rodar se este arquivo for executado diretamente
# isso evita que o loop infinito da Lucy ligue sozinho caso as funções sejam importadas em outro arquivo
if __name__ == "__main__":
    main()