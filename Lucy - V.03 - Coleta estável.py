# Projeto Lucy - Extração de informação de relatórios PDF e criação de JSON

# Bibliotecas usadas no projeto
import time # Para algumas funções que utilizam horário, é do próprio python
import os # Para poder conversar com o SO
import json # Precisa dela para a geração dos arquivos JSON que serão o log do projeto
import re # Vem de Regex, é especialista em padões, não procura palavras em si. É muito importante para capturar datas e números
import camelot # Especializada em extrair informações de PDF's em coordenadas espaciais (x e Y), uso em conjunto com a pypdf
from pypdf import PdfReader # Para trabalharmos com os PDF's, descobri ao longo de testes que ela n é boa com tabelas
from datetime import datetime, timedelta # O timedelta é para fazer as contas usando as horas, é bem útil
from pathlib import Path # Usada quando precisamos navegar por pastas de arquivos
from dotenv import load_dotenv # Para carregar o arquivo .env, com ele eu consigo trancar tudo e deixar o repositório público :D

# Carrega as variáveis do arquivo .env
load_dotenv()

# Criando as variáveis para as pastas, deixo tudo no dotenv tbm
pasta_pdf = os.getenv("PASTA_PDF")
pasta_json = os.getenv("PASTA_JSON")

# --------------------------------------------------------------------------------------------------------------------
# ********************************************************************************************************************
# --------------------------------------------------------------------------------------------------------------------

# O código é dividido por funções especializadas, cada uma responsável por uma parte

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
                
                def buscar_col(termos):
                    for i, c in enumerate(colunas):
                        if any(t.upper() in str(c).upper() for t in termos): return i
                    return -1

                idx_item = buscar_col(["ITEM"])
                idx_data = buscar_col(["DATA", "REMESSA"])
                idx_desc = buscar_col(["DESCRIÇÃO", "PRODUTO"])
                idx_valor = buscar_col(["TOTAL"])
                idx_reidi = buscar_col(["REIDI"])

                for _, linha in df_dados.iterrows():
                    
                    # Limpeza e Captura Básica
                    v_item = str(linha[idx_item]).strip() if idx_item != -1 else ""
                    
                    # Itens de pedido costumam ser 00010, 00020... 
                    # Se vier "UA", "TOTAL" ou vazio, a Lucy descarta na hora
                    if not v_item.isdigit():
                        continue
                    
                    # Capturando o RAIDI usando a lógica de verificação de dois fatores
                    # Pegamos a opinião da tabela (Trava de segurança)
                    reidi_tabela = "NÃO"
                    if idx_reidi != -1:
                        conteudo = str(linha[idx_reidi]).strip().upper()
                        
                        # só é SIM se estiver escrito SIM ou tiver um 'X'
                        if conteudo in ["SIM", "X", "S"]:
                            reidi_tabela = "SIM"
                    
                    # -------------------------------------------------------
                    # Decisão Final (Texto manda na Tabela)
                    # Se achamos a informação clara no texto (reidi_prioritario), usamos ela
                    # Se não achamos no texto, confiamos na tabela
                    
                    # Basicamente verifica se ele existe, ou se recebemos algo, 
                    # nesse caso é a mesma coisa que validar se ela chegou mesmo
                    if reidi_prioritario:
                        v_reidi = reidi_prioritario
                        print("🧐 Peguei a informação de REIDI do texto")
                    else:
                        v_reidi = reidi_tabela # Se ela não chegou então a gente confia na da tabela mesmo
                        print(" Não encontrei a informação de REIDI no texto, recorrendo a da tabela")
                    # -------------------------------------------------------
                    
                    # Captura dos outros campos
                    v_data = str(linha[idx_data]).strip() if idx_data != -1 else ""
                    v_valor = str(linha[idx_valor]).strip() if idx_valor != -1 else "0,00"
                    
                    # O [./] diz ao Python: "Procure um ponto OU uma barra aqui", as datas geralmente usam ponto nos PDF's
                    if not re.search(r"\d{2}[./]\d{2}[./]\d{4}", v_data):
                        continue

                    # E na hora de salvar, garantimos que no JSON vire sempre o modelo data com barra
                    data_formatada = v_data.replace(".", "/")

                    # Buscando pela descrição
                    def obter_desc_real(linha_atual, idx_base):
                        
                        # Candidatos: a coluna alvo, a anterior e a próxima
                        indices_para_testar = [idx_base, idx_base - 1, idx_base + 1]
                        
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
                    v_desc_bruta = obter_desc_real(linha, idx_desc)

                    # Lógica do Traço, com ela conseguimos separar a descrição e pegar apenas o número
                    partes = v_desc_bruta.split("-", 1)
                    if len(partes) > 1 and any(c.isdigit() for c in partes[0]):
                        descricao_final = partes[0].strip()
                    else:
                        descricao_final = v_desc_bruta

                    # Limpeza final de resquícios de "UA" que possam ter grudado, é importante pq os dados estavam misturando
                    descricao_final = re.sub(r"\s+UA\s+\d+", "", descricao_final, flags=re.IGNORECASE).strip()
                        
                    itens_pedido.append({
                        "item": v_item,
                        "data_remessa": v_data.replace(".", "/"),
                        "descricao": descricao_final,
                        "valor_total": v_valor,
                        "reidi": v_reidi
                    })
                    
    except Exception as e:
        print(f"⚠️ Erro no Camelot: {e}")
        
    return itens_pedido

# Função revisada para processar o cabeçalho e chamar o Camelot para a tabela
def processar_informacoes(texto_bruto, caminho_arquivo):
    
    # Captura de Campos Simples (Regex)
    match_pr = re.search(r"Nº do PR:\s*(.+)", texto_bruto)
    v_pr = match_pr.group(1).strip() if match_pr else "Não encontrado"

    match_data = re.search(r"Data:\s*(\d{2}[./-]\d{2}[./-]\d{4})", texto_bruto)
    v_data = match_data.group(1).replace(".", "/").replace("-", "/") if match_data else "Não encontrada"

    match_end = re.search(r"Dados de Faturamento\s+(.+?)(?=\s*CNPJ:)", texto_bruto, re.DOTALL)
    v_end = match_end.group(1).replace("\n", ", ").strip() if match_end else "Não encontrado"

    match_cnpj = re.search(r"CNPJ:\s*([\d\./-]+)", texto_bruto)
    v_cnpj = match_cnpj.group(1) if match_cnpj else "Não encontrado"

    match_ie = re.search(r"IE:\s*([\d.]+)", texto_bruto)
    v_ie = match_ie.group(1) if match_ie else "Não encontrado"
    
    # O Regex busca: número + parênteses + REIDI: + SIM ou NÃO, essaé a prioridade em cima da tabela, uma trava de segurança
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
                
                codigo_tabela = itens_pedido[0]['descricao'] if itens_pedido else ""
                
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
            print(f"🗺️  Região encontrada: {v_regiao} (Linha {linha_regiao})")
            print(f"📃 Contrato Identificado: {contrato_final}")

    except Exception as e:
        print(f"⚠️ Erro ao processar vizinhança: {e}")

    # Montagem final do Json, juntando tudo numa lista com dicionários
    dados_finais = {
        "cabecalho": {
            "numero_pr": v_pr,
            "data": v_data,
            "cnpj": v_cnpj,
            "ie": v_ie,
            "endereco": v_end
        },
        "itens_pedido": itens_pedido,
        "informacoes": {
            "contrato": contrato_final,
            "regiao": v_regiao
        }
    }
    return dados_finais
    
# Função responsável por pegar a hora atual do sistema, vai ajudar nas exibições, pega somente as horas e os minutos
def get_hora_atual() -> str:
    return datetime.now().strftime("%H:%M")

# --------------------------------------------------------------------------------------------------------------------
# ********************************************************************************************************************
# --------------------------------------------------------------------------------------------------------------------

# O corpo do projeto, vai ser responsável por iniciar as funções, a primeiro momento é um loop while infinito, mas pode mudar
# Dependendo dos próximos passos do projeto
def main():
    print(f"\n🪆  Lucy iniciando seus serviços - {get_hora_atual()}\n")
    
    pdfs_processados = set()

    while True:
        try:
            if not os.path.exists(pasta_pdf):
                print(f"⚠️ Pasta de PDF não encontrada: {pasta_pdf}")
                time.sleep(10)
                continue

            arquivos = os.listdir(pasta_pdf)
            novos_pdfs = [f for f in arquivos if f.endswith('.pdf') and f not in pdfs_processados]

            for nome_arquivo in novos_pdfs:
                caminho_completo = os.path.join(pasta_pdf, nome_arquivo)
                print("-" * 70)
                print(f"📍 Detectado: {nome_arquivo}")

                texto_pdf = extrair_texto_do_pdf(caminho_completo)
                
                if texto_pdf:
                    dados_extraidos = processar_informacoes(texto_pdf, caminho_completo)
                    
                    # Lógica para o nome do arquivo JSON: PR + Data (limpa para o formato que o Windows aceita)
                    pr_limpo = dados_extraidos["cabecalho"]["numero_pr"].replace("/", "-")
                    data_limpa = dados_extraidos["cabecalho"]["data"].replace("/", "-")
                    nome_json = f"PR_{pr_limpo}_{data_limpa}.json"
                    
                    caminho_salvamento = Path(pasta_json) / nome_json
                    os.makedirs(pasta_json, exist_ok=True)
                    
                    with open(caminho_salvamento, 'w', encoding='utf-8') as f:
                        json.dump(dados_extraidos, f, ensure_ascii=False, indent=4)
                    
                    print(f"✅ Dados de {nome_arquivo} salvos como {nome_json}")
                    print(("-" * 70) + "\n")
                    pdfs_processados.add(nome_arquivo)

        except Exception as e:
            print(f"⚠️ Erro na vigilância: {e}")

        time.sleep(5)

if __name__ == "__main__":
    main()