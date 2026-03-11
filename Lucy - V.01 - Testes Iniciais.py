# Projeto Lucy - Extração de informação de relatórios e criação de Json

# Bibliotecas usadas no projeto
import time
import os # Para poder conversar com o SO
import json # Precisamos dela para conseguirmos gerar os arquivos 
import re
from pypdf import PdfReader
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
 
# Função para processar os pdf um por um e extrair o necessário
def extrair_itens_tabela(texto):
        itens_extraidos = []
        
        # 1. Limpeza de Contexto: Ignora tudo antes da tabela real
        if "Frete:" in texto:
            texto = texto.split("Frete:")[1]

        # 2. O PULO DO GATO: Cortamos apenas em "Item" seguido de NÚMERO (Ex: Item 00010)
        # Isso faz com que o cabeçalho (que é só a palavra "Item") seja ignorado
        fatias = re.split(r"Item\s+(?=\d+)", texto, flags=re.IGNORECASE)
        
        for fatia in fatias[1:]:
            # --- BUSCAS INDEPENDENTES ---
            
            # Item: Pega a sequência numérica (mantendo os zeros)
            m_item = re.search(r"(\d+)", fatia)
            
            # Data: Padrão com pontos (conforme seu PDF)
            m_remessa = re.search(r"(\d{2}\.\d{2}\.\d{4})", fatia)
            
            # Valor Total: Busca o valor que vem após o título "Valor Total"
            m_valor = re.search(r"Valor Total\s+([\d.,]+)", fatia)
            
            # Unidade: Trava de segurança (UA, UN, PC, etc)
            m_unid = re.search(r"\s+(UA|UN|PC|KG|LT|M2)\s+", fatia)

            # --- DESCRIÇÃO ---
            # Como o cabeçalho vinha como "Unid Quant Valor", vamos mudar a âncora.
            # Vamos pegar o que está entre o NCM (números e pontos) e a Unidade.
            m_desc = re.search(r"\d{4}\.\d{2}\.\d{2}\s+(.*?)\s+(?=UA|UN|PC|KG|LT|M2)", fatia, re.DOTALL)
            
            # Se o NCM falhar, pegamos o que está entre a DATA e a UNIDADE
            if not m_desc and m_remessa:
                # Busca o texto que começa após a data e vai até a unidade
                m_desc = re.search(rf"{re.escape(m_remessa.group(1))}\s+.*?\s+(.*?)\s+(?=UA|UN|PC|KG|LT|M2)", fatia, re.DOTALL)

            # --- VALIDAÇÃO ---
            # Só aceita se tiver NÚMERO + DATA + UNIDADE
            if m_item and m_remessa and m_unid:
                
                # Lógica do REIDI
                m_reidi = re.search(r"REIDI\s*(.*?)(?=Local de Entrega|$)", fatia, re.DOTALL)
                conteudo_reidi = m_reidi.group(1).strip().upper() if m_reidi else ""
                reidi_status = "SIM" if any(x in conteudo_reidi for x in ["SIM", "X"]) else "NÃO"

                itens_extraidos.append({
                    "item": m_item.group(1), 
                    "data_remessa": m_remessa.group(1).replace(".", "/"),
                    "descricao": m_desc.group(1).replace("\n", " ").strip() if m_desc else "Não encontrada",
                    "valor_total": m_valor.group(1) if m_valor else "0,00",
                    "reidi": reidi_status
                })
        
        return itens_extraidos
    
    # --- 2. Extração dos campos simples (Variáveis Temporárias) ---
    
    # PR
    match_pr = re.search(r"Nº do PR:\s*(.+)", texto_bruto)
    v_pr = match_pr.group(1).strip() if match_pr else "Não encontrado"

    # Data
    match_data = re.search(r"Data:\s*(\d{2}[./-]\d{2}[./-]\d{4})", texto_bruto)
    v_data = match_data.group(1).replace(".", "/").replace("-", "/") if match_data else "Não encontrada"

    # Endereço
    match_end = re.search(r"Dados de Faturamento\s+(.+?)(?=\s*CNPJ:)", texto_bruto, re.DOTALL)
    v_end = match_end.group(1).replace("\n", ", ").strip() if match_end else "Não encontrado"

    # CNPJ e IE
    match_cnpj = re.search(r"CNPJ:\s*([\d\./-]+)", texto_bruto)
    v_cnpj = match_cnpj.group(1) if match_cnpj else "Não encontrado"

    match_ie = re.search(r"IE:\s*([\d.]+)", texto_bruto)
    v_ie = match_ie.group(1) if match_ie else "Não encontrado"

    # --- 3. Agora sim, montamos o dicionário final com tudo pronto ---
    dados_finais = {
        
        "cabecalho": {
        "numero_pr": v_pr,
        "data": v_data,
        "cnpj": v_cnpj,
        "ie": v_ie,
        "endereco": v_end
        },
        
        "itens_pedido": extrair_itens_tabela(texto_bruto)
    }

    return dados_finais
    
# Função responsável por pegar a hora atual do sistema, vai ajudar nas exibições, pega somente as horas e os minutos
def get_hora_atual() -> str:
    return datetime.now().strftime("%H:%M")

# --------------------------------------------------------------------------------------------------------------------
# ********************************************************************************************************************
# --------------------------------------------------------------------------------------------------------------------

def main():
    print(f"\n🪆  Lucy iniciando monitoramento - {get_hora_atual()}")
    
    pdfs_processados = set() # Usar set é mais rápido para buscas

    while True:
        try:
            arquivos = os.listdir(pasta_pdf)
            novos_pdfs = [f for f in arquivos if f.endswith('.pdf') and f not in pdfs_processados]

            for nome_arquivo in novos_pdfs:
                caminho_completo = os.path.join(pasta_pdf, nome_arquivo)
                print(f"📄 Detectado: {nome_arquivo}")

                # 1. Extrai o texto
                texto_pdf = extrair_texto_do_pdf(caminho_completo)
                
                if texto_pdf:
                    # 2. Extrai os dados específicos
                    dados_extraidos = processar_informacoes(texto_pdf)
                    
                    # 3. Salva o JSON (usando sua lógica de Path)
                    nome_json = nome_arquivo.replace(".pdf", ".json")
                    caminho_salvamento = Path(pasta_json) / nome_json
                    
                    with open(caminho_salvamento, 'w', encoding='utf-8') as f:
                        json.dump(dados_extraidos, f, ensure_ascii=False, indent=4)
                    
                    print(f"✅ Dados de {nome_arquivo} salvos em JSON.")
                    pdfs_processados.add(nome_arquivo)

        except Exception as e:
            print(f"⚠️  Erro na vigilância: {e}")

        time.sleep(5) # Lucy descansa um pouco mais para não sobrecarregar o PC

if __name__ == "__main__":
    main()