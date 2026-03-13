# Projeto Lucy - Extração de informação de relatórios e criação de Json

# Bibliotecas usadas no projeto
import time
import os # Para poder conversar com o SO
import json # Precisamos dela para conseguirmos gerar os arquivos 
import re
import pdfplumber # Especializada em extrair informações de PDF's com tabelas, ela vai completar o que n consegui com a pypdf, minha primeira tentativa fora o pypdf
import camelot # Usei ela nos meus segundos testes bucando uma validação final
from pypdf import PdfReader # Para trabalharmos com os PDF's, descobri ao longo de testes que ela n é boa com tabelas
from datetime import datetime, timedelta # O timedelta é para fazer as contas usando as horas, é bem útil
from pathlib import Path # Usada quando precisamos navegar por pastas de arquivos
from dotenv import load_dotenv # Para carregar o arquivo .env

# Carrega as variáveis do arquivo .env
load_dotenv()

# Criando as variáveis para as pastas, deixo tudo no dotenv tbm
pasta_pdf = os.getenv("PASTA_PDF")
pasta_json = os.getenv("PASTA_JSON")

# --------------------------------------------------------------------------------------------------------------------
# ********************************************************************************************************************
# --------------------------------------------------------------------------------------------------------------------

# O código é dividido por funções especializadas, cada uma responsável por uma parte
 
def extrair_texto_do_pdf(caminho_arquivo):
    try:
        reader = PdfReader(caminho_arquivo)
        texto_completo = ""
        for pagina in reader.pages:
            texto_completo += pagina.extract_text()
        return texto_completo
    except Exception as e:
        print(f"❌ Erro ao ler o arquivo {caminho_arquivo}: {e}")
        return None

def extrair_tabela_com_camelot(caminho_arquivo):
    itens_pedido = []
    
    try:
        # --- O AJUSTE DE OURO ---
        # Definimos onde cada coluna 'nasce' no eixo X (da esquerda para a direita)
        # Exemplo: Item começa em 50, Req em 80, Data em 120...
        # Você vai ajustar esses números baseados no seu PDF
        minhas_colunas = '60, 100, 150, 230, 280, 380, 420, 460, 520' 

        tabelas = camelot.read_pdf(
            caminho_arquivo, 
            pages='1', 
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
                # Removemos tudo o que vem antes do cabeçalho
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
                    # 1. Limpeza e Captura Básica
                    v_item = str(linha[idx_item]).strip() if idx_item != -1 else ""
                    
                    # --- TRAVA 1: O ITEM PRECISA SER UM NÚMERO PURO ---
                    # Itens de pedido costumam ser 00010, 00020... 
                    # Se vier "UA", "TOTAL" ou vazio, a Lucy descarta na hora.
                    if not v_item.isdigit():
                        continue

                    # 2. Captura dos outros campos
                    v_data = str(linha[idx_data]).strip() if idx_data != -1 else ""
                    v_valor = str(linha[idx_valor]).strip() if idx_valor != -1 else "0,00"
                    
                    # --- TRAVA 2 CORRIGIDA: ACEITA PONTO OU BARRA ---
                    # O [./] diz ao Python: "Procure um ponto OU uma barra aqui"
                    if not re.search(r"\d{2}[./]\d{2}[./]\d{4}", v_data):
                        continue

                    # E na hora de salvar, garantimos que no JSON vire sempre barra (padrão que você prefere)
                    data_formatada = v_data.replace(".", "/")

                    # --- BUSCA INTELIGENTE DE DESCRIÇÃO ---
                    def obter_desc_real(linha_atual, idx_base):
                        # Candidatos: a coluna alvo, a anterior e a próxima
                        indices_para_testar = [idx_base, idx_base - 1, idx_base + 1]
                        
                        for idx in indices_para_testar:
                            # Pula se o índice for inválido para esta linha
                            if idx < 0 or idx >= len(linha_atual):
                                continue
                                
                            texto = str(linha_atual[idx]).replace("\n", " ").strip()
                            
                            # FILTRO: Só aceitamos se NÃO for "UA", NÃO for só número e tiver tamanho
                            if texto and not texto.upper().startswith("UA") and not texto.isdigit() and len(texto) > 3:
                                return texto
                        return "Descrição não localizada"

                    # Aplicando a busca
                    v_desc_bruta = obter_desc_real(linha, idx_desc)

                    # Lógica do Traço (Sua regra de ouro para limpar o código do produto)
                    partes = v_desc_bruta.split("-", 1)
                    if len(partes) > 1 and any(c.isdigit() for c in partes[0]):
                        descricao_final = partes[0].strip()
                    else:
                        descricao_final = v_desc_bruta

                    # Limpeza final de resquícios de "UA" que possam ter grudado
                    descricao_final = re.sub(r"\s+UA\s+\d+", "", descricao_final, flags=re.IGNORECASE).strip()
                        
                    itens_pedido.append({
                        "item": v_item,
                        "data_remessa": v_data.replace(".", "/"),
                        "descricao": descricao_final,
                        "valor_total": v_valor,
                        "reidi": "SIM" if idx_reidi != -1 and "SIM" in str(linha[idx_reidi]).upper() else "NÃO"
                    })
                    
    except Exception as e:
        print(f"⚠️ Erro no Camelot: {e}")
        
    return itens_pedido

# Função revisada para processar o cabeçalho e chamar o Camelot para a tabela
def processar_informacoes(texto_bruto, caminho_arquivo):
    # 1. Captura de Campos Simples (Regex)
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

    # Extração da tabela feita pelo Camelot e atribuição a uma variável
    itens_pedido = extrair_tabela_com_camelot(caminho_arquivo)

    # --- 3. INFORMAÇÕES ADICIONAIS (Via Camelot) ---
    pedido_final = "Não encontrado"
    v_regiao = "Não encontrada"

    try:
        # Lemos a página novamente, mas sem forçar as colunas da tabela principal
        # para deixar a Camelot achar o rodapé livremente
        todas_as_tabelas = camelot.read_pdf(caminho_arquivo, pages='1', flavor='stream')
        
        if todas_as_tabelas.n > 0:
            # Pegamos a ÚLTIMA tabela (geralmente é onde fica o rodapé/notas)
            df_rodape = todas_as_tabelas[-1].df
            
            # Transformamos tudo em uma string gigante para busca
            texto_rodape = " ".join(df_rodape.astype(str).values.flatten())
            
            # 1. Busca do Pedido (Filtro de Exclusão)
            # Buscamos números de 8 a 12 dígitos
            nums = re.findall(r"\b\d{8,12}\b", texto_rodape)
            codigo_tabela = itens_pedido[0]['descricao'] if itens_pedido else ""
            
            for n in nums:
                # Se não for o PR, não for o código da descrição e não começar com 0 (telefone)
                if n != v_pr and n not in codigo_tabela and not n.startswith('0'):
                    pedido_final = n
                    break
            
            # 2. Busca da Região (Foco no #)
            # Procuramos o que vem após o # dentro dessa estrutura de tabela
            match_reg = re.search(r"#\s*([^\n\r]+)", texto_rodape)
            if match_reg:
                v_regiao = match_reg.group(1).split("  ")[0].strip() 
            else:
                # Se não achar o #, procuramos por padrões de Região (Ex: SE ASSIS)
                match_padrao = re.search(r"([A-Z]{2}\s+[A-Z]+(?:\s+[A-Z]+)*)", texto_rodape)
                if match_padrao:
                    v_regiao = match_padrao.group(1).strip()

    except Exception as e:
        print(f"⚠️ Erro ao buscar rodapé com Camelot: {e}")

    # --- 4. MONTAGEM FINAL DO JSON ---
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
            "numero_pedido": pedido_final,
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

def main():
    print(f"\n🪆  Lucy iniciando monitoramento - {get_hora_atual()}\n")
    
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
                print(f"📄 Detectado: {nome_arquivo}")

                texto_pdf = extrair_texto_do_pdf(caminho_completo)
                
                if texto_pdf:
                    dados_extraidos = processar_informacoes(texto_pdf, caminho_completo)
                    
                    # Lógica para o nome do arquivo JSON: PR + Data (limpa)
                    pr_limpo = dados_extraidos["cabecalho"]["numero_pr"].replace("/", "-")
                    data_limpa = dados_extraidos["cabecalho"]["data"].replace("/", "-")
                    nome_json = f"PR_{pr_limpo}_{data_limpa}.json"
                    
                    caminho_salvamento = Path(pasta_json) / nome_json
                    os.makedirs(pasta_json, exist_ok=True)
                    
                    with open(caminho_salvamento, 'w', encoding='utf-8') as f:
                        json.dump(dados_extraidos, f, ensure_ascii=False, indent=4)
                    
                    print(f"✅ Dados de {nome_arquivo} salvos como {nome_json}\n")
                    pdfs_processados.add(nome_arquivo)

        except Exception as e:
            print(f"⚠️ Erro na vigilância: {e}")

        time.sleep(5)

if __name__ == "__main__":
    main()