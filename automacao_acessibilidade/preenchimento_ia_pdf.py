import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog
import os
import sys
import requests
import json
import traceback
import threading
import hashlib
import logging
from datetime import datetime
import re
import webbrowser

try:
    import fitz
    TEM_PYMUPDF = True
except ImportError:
    try:
        import PyPDF2
        TEM_PYMUPDF = False
    except ImportError:
        TEM_PYMUPDF = None

try:
    import speech_recognition as sr
    TEM_SPEECH_RECOGNITION = True
except ImportError:
    TEM_SPEECH_RECOGNITION = False
def resource_path(rel: str) -> str:
    """Retorna caminho do recurso (funciona no .exe e no .py)."""
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)





# ==========================================
# 1. CONFIGURAÇÕES, CAMINHOS E LOG
# ==========================================
ctk.set_appearance_mode("Light")
ctk.set_default_color_theme("blue")

PASTA_ATUAL = (
    os.path.dirname(sys.executable)
    if getattr(sys, 'frozen', False)
    else os.path.dirname(os.path.abspath(__file__))
)
CAMINHO_TXT      = os.path.join(PASTA_ATUAL, "dados_dds.txt")
CAMINHO_HTML     = os.path.join(PASTA_ATUAL, "resumo_dds_app.html")
CAMINHO_HTML_BONECO = os.path.join(PASTA_ATUAL, "resumo_dds_boneco.html")
CAMINHO_CONFIG   = os.path.join(PASTA_ATUAL, "config.json")
CAMINHO_CACHE    = os.path.join(PASTA_ATUAL, ".ia_cache.json")
CAMINHO_AUTOSAVE = os.path.join(PASTA_ATUAL, ".autosave.json")
CAMINHO_LOG      = os.path.join(PASTA_ATUAL, "dds_app.log")

logging.basicConfig(
    filename=CAMINHO_LOG,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    encoding='utf-8'
)
log = logging.getLogger("DDS")

CONFIG_PADRAO = {
    "ollama_url": "http://localhost:11434/api/generate",
    "ollama_tags_url": "http://localhost:11434/api/tags",
    "modelo_ia": "narrador-dds",
    "timeout_ia": 120,
    "autosave_segundos": 30,
    "thresholds": {
        "d1_max":   0.13,
        "ftt_min":  99.80,
        "mves_max": 0.30,
        "_5s_min":  90
    }
}

def carregar_config():
    if not os.path.exists(CAMINHO_CONFIG):
        with open(CAMINHO_CONFIG, "w", encoding="utf-8") as f:
            json.dump(CONFIG_PADRAO, f, indent=4, ensure_ascii=False)
        return CONFIG_PADRAO
    try:
        with open(CAMINHO_CONFIG, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        # mescla com padrão (robusto a chaves faltando)
        for k, v in CONFIG_PADRAO.items():
            if k not in cfg:
                cfg[k] = v
            elif isinstance(v, dict):
                for kk, vv in v.items():
                    cfg[k].setdefault(kk, vv)
        return cfg
    except Exception as e:
        log.error(f"Falha ao ler config.json: {e}")
        return CONFIG_PADRAO

CONFIG = carregar_config()

MAPA_DIAS = {
    'Monday': 'SEGUNDA', 'Tuesday': 'TERÇA',  'Wednesday': 'QUARTA',
    'Thursday': 'QUINTA', 'Friday': 'SEXTA',  'Saturday': 'SÁBADO',
    'Sunday': 'DOMINGO'
}

# ==========================================
# 2. CACHE DE RESPOSTAS IA
# ==========================================
def _carregar_cache() -> dict:
    if not os.path.exists(CAMINHO_CACHE):
        return {}
    try:
        with open(CAMINHO_CACHE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _salvar_cache(cache: dict):
    try:
        with open(CAMINHO_CACHE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception as e:
        log.warning(f"Cache não salvo: {e}")

CACHE_IA = _carregar_cache()

def _hash_prompt(prompt: str, system: str | None) -> str:
    h = hashlib.sha1()
    h.update((system or "").encode("utf-8"))
    h.update(b"||")
    h.update(prompt.encode("utf-8"))
    h.update(CONFIG["modelo_ia"].encode("utf-8"))
    return h.hexdigest()

# ==========================================
# 3. PRÉ-PROCESSAMENTO
# ==========================================
SUBSTITUICOES = {
    "prensamento":"dedo preso","prensagem":"aperto","hidratação":"beber água",
    "ergonomia":"postura correta","ergonômico":"posição segura","ergonômica":"posição segura",
    "contaminação":"sujeira","escorrimento":"tinta escorrida","calibração":"ajuste",
    "sequenciamento":"ordem correta","abastecimento":"entrega de peças",
    "não-conformidade":"defeito","não conformidade":"defeito","anormalidade":"problema",
    "dispositivo":"suporte","segregado":"separado","segregação":"separação",
    "retrabalho":"corrigir","checklist":"lista de verificação",
    "inspeção tátil":"verificar com mão","contenção":"separar e controlar",
    "demarcado":"local marcado","demarcação":"local marcado","fixação":"prender peça",
    "superfície":"parte de fora","resíduo":"sujeira","resíduos":"sujeiras",
    "obstrução":"passagem bloqueada","procedimento":"padrão","atividade":"trabalho",
    "colaborador":"trabalhador","colaboradores":"trabalhadores",
    "impróprio":"errado","inadequado":"errado",
}

def substituir_palavras_proibidas(t: str) -> str:
    for p, s in SUBSTITUICOES.items():
        t = re.sub(re.escape(p), s, t, flags=re.IGNORECASE)
    return t

def truncar_texto(t: str, max_chars: int = 300) -> str:
    if len(t) <= max_chars: return t
    c = t[:max_chars]; p = c.rfind('.')
    return c[:p + 1] if p > max_chars // 2 else c.strip() + "..."

def limpar_texto_campo(t: str, max_chars: int = 300) -> str:
    if not t: return ""
    return truncar_texto(substituir_palavras_proibidas(t), max_chars).strip()

def limpar_resposta_ia(t: str) -> str:
    if not t: return ""
    padroes = re.compile(r'^(aqui est[áa]|segue|tradu|resumo|nota:|obs:|here is|here\'s)', re.IGNORECASE)
    limpas = []
    for ln in t.split('\n'):
        l = ln.strip()
        if not l:
            if limpas and limpas[-1] != '': limpas.append('')
            continue
        if padroes.match(l.lower()): continue
        l = re.sub(r'\*+|`+', '', l).strip()
        if l: limpas.append(l)
    r = '\n'.join(limpas)
    r = re.sub(r'\b(graus?|°)\b\.?', '', r, flags=re.IGNORECASE)
    r = re.sub(r' +', ' ', r); r = re.sub(r' +\.', '.', r)
    resultado = corrigir_unidades_dds(resultado)
    return re.sub(r'\n{3,}', '\n\n', resultado).strip()
    return re.sub(r'\n{3,}', '\n\n', r).strip()     
def corrigir_unidades_dds(texto: str) -> str:
    """Pós-processa saída da IA para evitar erros do VLibras."""
    # 1. Remove duplicações "por cento por cento" / "porcento porcento"
    texto = re.sub(
        r'\b(por\s*cento|porcento)\s+(por\s*cento|porcento)\b',
        'porcento', texto, flags=re.IGNORECASE
    )

    # 2. Remove "por cento"/"porcento" após D1
    texto = re.sub(
        r'(\bD1\b[^.\n]*?)\s*(por\s*cento|porcento)',
        r'\1', texto, flags=re.IGNORECASE
    )

    # 3. Remove "por cento"/"porcento" após MVES
    texto = re.sub(
        r'(\bMVES\b[^.\n]*?)\s*(por\s*cento|porcento)',
        r'\1', texto, flags=re.IGNORECASE
    )

    # 4. 🎯 Garante "porcento" junto (VLibras sinaliza melhor)
    texto = re.sub(r'\bpor\s+cento\b', 'porcento', texto, flags=re.IGNORECASE)

    # 5. Limpeza
    texto = re.sub(r' +', ' ', texto)
    texto = re.sub(r' +\.', '.', texto)
    return texto
    # Limpeza de espaços
    texto = re.sub(r' +', ' ', texto)
    texto = re.sub(r' +\.', '.', texto)
    return texto 



def limpar_resposta_ia(t: str) -> str:
    if not t:
        return ""
    padroes = re.compile(
        r'^(aqui est[áa]|segue|tradu|resumo|nota:|obs:|here is|here\'s)',
        re.IGNORECASE
    )
    limpas = []
    for ln in t.split('\n'):
        l = ln.strip()
        if not l:
            if limpas and limpas[-1] != '':
                limpas.append('')
            continue
        if padroes.match(l.lower()):
            continue
        l = re.sub(r'\*+|`+', '', l).strip()
        if l:
            limpas.append(l)

    r = '\n'.join(limpas)
    r = re.sub(r'\b(graus?|°)\b\.?', '', r, flags=re.IGNORECASE)
    r = re.sub(r' +', ' ', r)
    r = re.sub(r' +\.', '.', r)
    r = corrigir_unidades_dds(r)              # ✅ pós-processamento
    return re.sub(r'\n{3,}', '\n\n', r).strip()

#============
# 4. LÓGICA DE NEGÓCIO
# ==========================================
def calcular_bandeiras(dados: dict) -> dict:
    t = CONFIG.get("thresholds", {})
    d1_max   = t.get("d1_max",   0.13)
    ftt_min  = t.get("ftt_min",  99.80)
    mves_max = t.get("mves_max", 0.30)
    s5_min   = t.get("_5s_min",  90)

    b_seg  = "verde" if dados['num_ocorrencias'] == 0 else "vermelha"
    b_d1   = "verde" if dados['d1_g']   <= d1_max  else "vermelha"
    b_ftt  = "verde" if dados['ftt_g']  >= ftt_min else "vermelha"
    b_mves = "verde" if dados['mves_g'] <= mves_max else "vermelha"
    b_qual = "verde" if all(b == "verde" for b in [b_d1, b_ftt, b_mves]) else "vermelha"
    b_prod = "verde" if dados['prod_real'] >= dados['prod_meta'] else "vermelha"
    b_5s   = "verde" if dados['nota_5s'] >= s5_min else "vermelha"
    b_geral = "vermelha" if "vermelha" in [b_seg, b_qual, b_prod, b_5s] else "verde"

    return {"seg": b_seg, "d1": b_d1, "ftt": b_ftt, "mves": b_mves,
            "qual": b_qual, "prod": b_prod, "s5": b_5s, "geral": b_geral}

def montar_json_dds(dados: dict) -> dict:
    num_ocor = dados['num_ocorrencias']
    desc_seg = dados['desc_ocorrencia']
    msg_seg = desc_seg if desc_seg else ("" if num_ocor == 0 else f"{num_ocor} ocorrência registrada.")
    b = calcular_bandeiras(dados)
    return {
        "dialogo_dia": dados['msg_pdf'],
        "seguranca": {"ocorrencias": num_ocor, "descricao": msg_seg, "bandeira": b["seg"]},
        "qualidade": {
            "d1": dados['d1_g'], "d1_foco": dados['item_d1'], "d1_bandeira": b["d1"],
            "ftt": dados['ftt_g'], "ftt_foco": dados['item_ftt'], "ftt_bandeira": b["ftt"],
            "mves": dados['mves_g'], "mves_foco": dados['item_mves'], "mves_bandeira": b["mves"],
            "bandeira": b["qual"]
        },
        "producao": {"real": dados['prod_real'], "meta": dados['prod_meta'], "bandeira": b["prod"]},
        "cinco_s":  {"nota": dados['nota_5s'], "descricao": dados['desc_5s'], "bandeira": b["s5"]},
        "mensagem_lideranca": dados.get('msg_lideranca', ''),
        "bandeira_geral": b["geral"],
        "prioridade": dados['prio']
    }

# ==========================================
# 5. COMUNICAÇÃO COM IA (com cache + cancel)
# ==========================================
CANCELAR_FLAG = {"valor": False}

def ollama_online() -> tuple[bool, str]:
    try:
        r = requests.get(CONFIG["ollama_tags_url"], timeout=3)
        if r.status_code != 200:
            return False, f"Status {r.status_code}"
        modelos = [m["name"] for m in r.json().get("models", [])]
        if not any(CONFIG["modelo_ia"] in m for m in modelos):
            return False, f"Modelo '{CONFIG['modelo_ia']}' não encontrado. Modelos disponíveis: {', '.join(modelos) or 'nenhum'}"
        return True, "OK"
    except Exception as e:
        return False, str(e)

def chamar_ia(prompt: str, system_prompt: str = None, usar_cache: bool = True) -> str | None:
    if CANCELAR_FLAG["valor"]:
        return None

    chave = _hash_prompt(prompt, system_prompt)
    if usar_cache and chave in CACHE_IA:
        log.info(f"Cache hit: {chave[:10]}")
        return CACHE_IA[chave]

    payload = {"model": CONFIG["modelo_ia"], "prompt": prompt, "stream": False}
    if system_prompt:
        payload["system"] = system_prompt

    try:
        t0 = datetime.now()
        r = requests.post(CONFIG["ollama_url"], json=payload, timeout=CONFIG["timeout_ia"])
        dt = (datetime.now() - t0).total_seconds()
        if r.status_code == 200:
            resposta = limpar_resposta_ia(r.json().get("response", "").strip())
            log.info(f"IA OK em {dt:.1f}s ({len(resposta)} chars)")
            if usar_cache and resposta:
                CACHE_IA[chave] = resposta
                _salvar_cache(CACHE_IA)
            return resposta
        log.error(f"IA HTTP {r.status_code}: {r.text[:200]}")
    except requests.exceptions.Timeout:
        log.error("IA timeout")
    except Exception as e:
        log.error(f"IA erro: {e}")
    return None

def gerar_texto_via_ia(json_dds: dict) -> str:
    prompt = json.dumps(json_dds, ensure_ascii=False)
    resposta = chamar_ia(prompt)
    if resposta and len(resposta) > 50:
        return resposta
    log.warning("Usando fallback Python (IA falhou ou resposta curta)")
    return gerar_fallback(json_dds)

def gerar_fallback(j: dict) -> str:
    seg, qual, prod, s5 = j['seguranca'], j['qualidade'], j['producao'], j['cinco_s']
    msg_lid = j.get('mensagem_lideranca', '').strip()
    ocor_txt = "Não houve ocorrência ontem." if seg['ocorrencias'] == 0 else f"Houve {seg['ocorrencias']} ocorrência ontem."
    bloco_lid = f"\n\nMensagem da liderança.\n{msg_lid}" if msg_lid else ""
    return f"""Bom dia. Reunião DDS agora.

Diálogo do dia.
{j.get('dialogo_dia', '')}

Segurança.
{ocor_txt}
{('Descrição: ' + seg['descricao'] + '.') if seg['descricao'] else ''}
Bandeira segurança: {seg['bandeira']}.

Qualidade.
D1 {qual['d1']}.{(' Foco ' + qual['d1_foco'] + '.') if qual['d1_foco'] else ''}
Bandeira D1: {qual['d1_bandeira']}.
FTT {qual['ftt']} por cento.{(' Foco ' + qual['ftt_foco'] + '.') if qual['ftt_foco'] else ''}
Bandeira FTT: {qual['ftt_bandeira']}.
MVES {qual['mves']}.{(' Foco ' + qual['mves_foco'] + '.') if qual['mves_foco'] else ''}
Bandeira MVES: {qual['mves_bandeira']}.
Bandeira qualidade: {qual['bandeira']}.

Produção.
Ontem produção real {prod['real']} unidades. Meta {prod['meta']} unidades.
Bandeira produção: {prod['bandeira']}.

Organização e limpeza cinco s.
Nota {s5['nota']} por cento.{(' Realizar amanhã: ' + s5['descricao'] + '.') if s5['descricao'] else ''}
Bandeira cinco s: {s5['bandeira']}.{bloco_lid}

Resultado geral.
Bandeira geral: {j['bandeira_geral']}.
Prioridade {j['prioridade'].lower()}.

Obrigado. Bom trabalho."""

# ==========================================
# 6. EXTRAÇÃO PDF
# ==========================================
def extrair_mensagem_pdf(caminho_pdf: str):
    try:
        dia_pt = MAPA_DIAS.get(datetime.now().strftime("%A"), "").upper()
        texto_completo = ""
        if TEM_PYMUPDF is True:
            with fitz.open(caminho_pdf) as doc:
                for page in doc:
                    texto_completo += page.get_text() + "\n"
        elif TEM_PYMUPDF is False:
            with open(caminho_pdf, 'rb') as f:
                for page in PyPDF2.PdfReader(f).pages:
                    texto_completo += (page.extract_text() or "") + "\n"
        else:
            return None, None

        texto_upper = texto_completo.upper()
        matches = list(re.finditer(r'(SEGUNDA|TER[ÇC]A|QUARTA|QUINTA|SEXTA|S[ÁA]BADO|DOMINGO)\s*-\s*FEIRA', texto_upper))

        if not matches:
            linhas = [l.strip() for l in texto_completo.split('\n') if l.strip()]
            return limpar_texto_campo('\n'.join(linhas[:15]), max_chars=600), "PDF Geral"

        inicio = fim = -1
        for i, m in enumerate(matches):
            if dia_pt in m.group(0):
                inicio = m.end()
                fim = matches[i + 1].start() if i + 1 < len(matches) else len(texto_completo)
                break
        if inicio == -1:
            return f"Não foi encontrado texto para {dia_pt}-FEIRA neste PDF.", "Aviso"
        msg = re.sub(r'\s+', ' ', texto_completo[inicio:fim]).strip()
        return limpar_texto_campo(msg, max_chars=600), f"{dia_pt}-FEIRA"
    except Exception as e:
        log.error(f"PDF: {e}")
        return None, None

# ==========================================
# 7. AVATAR LIBRAS HTML
# ==========================================
def rodar_apresentacao_libras(texto_bruto=None):
    """Abre o boneco de Libras. Se texto_bruto vier vazio, le o dados_dds.txt
    (fluxo do DDS diario); se vier preenchido, apresenta esse texto direto
    (usado pelo tradutor de voz)."""
    if texto_bruto is None:
        if not os.path.exists(CAMINHO_TXT):
            messagebox.showwarning("Aviso", "Arquivo de texto não encontrado.")
            return
        with open(CAMINHO_TXT, "r", encoding="utf-8") as f:
            texto_bruto = f.read()
    texto = texto_bruto.replace("\n", ". ").replace('"', '&quot;').replace("'", "&#39;")

    # Pagina interna: contem o widget do VLibras de verdade. Fica numa janela
    # "estreita" (nested_width) para que o botao "Expandir" do proprio widget
    # produza um cartao com o corpo inteiro do boneco bem proporcionado.
    html_boneco = f"""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8"><title>Boneco</title>
<style>
*{{margin:0!important;padding:0!important;box-sizing:border-box!important}}
html,body{{width:100vw;height:100vh;overflow:hidden!important;background:#1a1a2e}}
#alvo{{position:fixed;top:5px;left:5px;opacity:0.01;z-index:1;pointer-events:auto;font-size:1px}}
</style></head><body>
<div id="alvo">{texto}</div>
<script src="https://vlibras.gov.br/app/vlibras-plugin.js"></script>
<script>
new window.VLibras.Widget('https://vlibras.gov.br/app');
function abrirBoneco(){{
var wrap=document.getElementById('vlibras-access-wrapper');
var btn=wrap&&wrap.shadowRoot?wrap.shadowRoot.querySelector('#vlibras-button'):null;
if(btn){{btn.click();return true;}}
return false;
}}
function expandirBoneco(){{
var root=document.getElementById('vlibras-app-root');
var btn=root&&root.shadowRoot?root.shadowRoot.querySelector('button[aria-label="Expandir"]'):null;
if(btn){{btn.click();return true;}}
return false;
}}
function pularBoneco(){{
var root=document.getElementById('vlibras-app-root');
var sr=root&&root.shadowRoot?root.shadowRoot:null;
if(!sr)return false;
var btns=Array.from(sr.querySelectorAll('button'));
var btn=btns.find(function(b){{return b.textContent.trim()==='Pular';}});
if(btn){{btn.click();return true;}}
return false;
}}
function avatarPronto(){{
// O atributo data-status do widget fica "idle" poucos segundos apos abrir,
// bem antes do avatar 3D (pesado) realmente terminar de carregar -- entao
// nao serve como sinal. O iframe do avatar, porem, comeca com opacity:0 e
// so vira opacity:1 quando ele de fato terminou de carregar e esta pronto
// para receber texto. Usamos isso para nao esperar mais tempo que o
// necessario antes de mandar o texto do DDS.
var root=document.getElementById('vlibras-app-root');
var sr=root&&root.shadowRoot?root.shadowRoot:null;
if(!sr)return false;
var iframe=sr.querySelector('iframe[title="vlibras-player"]');
if(!iframe)return false;
return parseFloat(getComputedStyle(iframe).opacity)>=1;
}}
window.addEventListener('load',function(){{
var tentativas=0,abriu=false,expandiu=false,prontoCount=0,despachado=false;
function disparar(){{
var el=document.getElementById('alvo');el.style.fontSize='16px';el.style.width='auto';el.style.height='auto';
var range=document.createRange();range.selectNodeContents(el);var sel=window.getSelection();sel.removeAllRanges();sel.addRange(range);
el.dispatchEvent(new MouseEvent('mouseup',{{bubbles:true}}));el.dispatchEvent(new MouseEvent('click',{{bubbles:true}}));
}}
var esperaBotao=setInterval(function(){{
tentativas++;
if(!abriu)abriu=abrirBoneco();
if(abriu&&!expandiu)expandiu=expandirBoneco();
if(expandiu)pularBoneco();
if(expandiu&&!despachado){{
if(avatarPronto()){{prontoCount++;}}else{{prontoCount=0;}}
if(prontoCount>=4){{despachado=true;disparar();}}
}}
if(despachado||tentativas>200){{clearInterval(esperaBotao);}}
}},250);
// Rede de seguranca: se por algum motivo a deteccao acima falhar, garante
// que o texto seja lido mesmo assim depois de um tempo generoso.
setTimeout(function(){{if(!despachado){{despachado=true;disparar();}}}},45000);
}});
// Se esta janela for tapada/minimizada durante a apresentacao (por outra
// janela por cima, notificacao do Windows, etc.), o Chrome/Edge marca a
// pagina como oculta e o proprio VLibras pausa o boneco no meio da frase --
// era a causa do boneco "cortar" o que estava falando. Assim que a janela
// volta a ficar visivel, retomamos de onde parou (sem reiniciar a frase).
document.addEventListener('visibilitychange',function(){{
if(document.visibilityState==='visible'){{
var v=window.vlibras;
if(v&&v.status==='paused'&&!v.isPausedByUser){{v.play();}}
}}
}});
</script></body></html>"""
    with open(CAMINHO_HTML_BONECO, "w", encoding="utf-8") as f:
        f.write(html_boneco)

    # Pagina externa: a que o navegador realmente abre. Ela hospeda a pagina
    # interna dentro de um iframe estreito (pre-rotacionado) e depois usa
    # CSS para girar 90 graus e ampliar esse iframe até preencher a tela
    # real inteira. Isso e o que faz o boneco aparecer deitado (pes para um
    # lado, cabeca para o outro) e, quando o monitor fisico e girado sem
    # mexer na configuracao do Windows, o boneco aparece de pe e em tela
    # cheia para quem esta assistindo.
    html_externo = """<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8"><title>HPE-DDS LIBRAS</title>
<style>
*{margin:0!important;padding:0!important;box-sizing:border-box!important}
html,body{width:100vw;height:100vh;overflow:hidden!important;background:#1a1a2e}
#frame{position:fixed;border:none;background:#1a1a2e;}
</style></head><body>
<iframe id="frame" src="resumo_dds_boneco.html"></iframe>
<script>
function ajustar(){
var RW = window.innerWidth, RH = window.innerHeight;
// Tamanho fixo (em pixels) do cartao "Expandir" do proprio widget do VLibras.
// Nao e proporcional -- o widget sempre renderiza nesse tamanho exato,
// entao usamos esses mesmos valores aqui para nao sobrar nem faltar espaco.
var cardW = 576, cardH = 852.8;
// "Cover": amplia o suficiente para cobrir a tela toda em qualquer
// resolucao, mesmo que isso corte um pouco as bordas do cartao.
var scale = Math.max(RW/cardH, RH/cardW);
var f = document.getElementById('frame');
f.style.width = cardW+'px';
f.style.height = cardH+'px';
f.style.top = '50%';
f.style.left = '50%';
f.style.transformOrigin = 'center center';
f.style.transform = 'translate(-50%,-50%) rotate(90deg) scale('+scale+')';
}
ajustar();
window.addEventListener('resize', ajustar);
</script>
</body></html>"""
    with open(CAMINHO_HTML, "w", encoding="utf-8") as f:
        f.write(html_externo)
    webbrowser.open(f'file:///{os.path.abspath(CAMINHO_HTML)}')

# ==========================================
# 8. INTERFACE GRÁFICA
# ==========================================
class DDSAppIA(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("HPE - Gestão DDS Acessível")
        self.geometry("960x980")
        self.protocol("WM_DELETE_WINDOW", self.ao_fechar)
        self.vars = {}
        self.thread_atual = None
        self._criar_interface()
        self._registrar_atalhos()
        self._restaurar_autosave()
        self.after(500, self._verificar_ollama_inicial)
        self.after(CONFIG["autosave_segundos"] * 1000, self._autosave)

    def ao_fechar(self):
        self._salvar_autosave()
        if getattr(self, '_ouvindo_voz', False):
            self._parar_gravacao_voz()
        self.quit(); self.destroy(); sys.exit(0)

    # ------------------------------------------
    # ATALHOS
    # ------------------------------------------
    def _registrar_atalhos(self):
        self.bind("<Control-o>", lambda e: self._otimizar_assincrono())
        self.bind("<Control-p>", lambda e: self._preview_assincrono())
        self.bind("<Control-s>", lambda e: self._salvar_e_executar())
        self.bind("<Escape>",    lambda e: self._cancelar())

    # ------------------------------------------
    # INTERFACE
    # ------------------------------------------
    def _criar_interface(self):
        # Header
        header = ctk.CTkFrame(self, fg_color="#d32f2f", corner_radius=0)
        header.pack(fill="x")
        ctk.CTkLabel(header, text="📊 GESTÃO DDS ACESSÍVEL",
                     font=("Segoe UI", 20, "bold"), text_color="white").pack(pady=12)
        self.lbl_status_ia = ctk.CTkLabel(header, text="⏳ Verificando Ollama...",
                                          text_color="white", font=("Segoe UI", 10))
        self.lbl_status_ia.pack(pady=(0, 8))

        # Barra de status / progresso (rodapé)
        rodape = ctk.CTkFrame(self, fg_color="#eeeeee", corner_radius=0, height=42)
        rodape.pack(fill="x", side="bottom")
        self.lbl_status = ctk.CTkLabel(rodape, text="Pronto.", anchor="w",
                                       font=("Segoe UI", 10), text_color="#333")
        self.lbl_status.pack(side="left", padx=10)
        self.progresso = ctk.CTkProgressBar(rodape, width=240, mode="indeterminate")
        self.progresso.pack(side="right", padx=10, pady=8)
        self.progresso.set(0)

        # Abas: DDS diário e Tradutor de Voz
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)
        tab_dds = self.tabview.add("📋 DDS")
        tab_voz = self.tabview.add("🎤 Tradutor de Voz")

        self.scroll = ctk.CTkScrollableFrame(tab_dds, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True)

        self._criar_aba_voz(tab_voz)

        # Seção 0 — PDF
        self._secao("0️⃣  DIÁLOGO DE SEGURANÇA DO DIA (PDF)")
        f_pdf = ctk.CTkFrame(self.scroll, fg_color="transparent")
        f_pdf.pack(fill="x", padx=10, pady=5)
        ctk.CTkButton(f_pdf, text="📂 Carregar PDF", command=self._carregar_pdf,
                      fg_color="#ff9800", text_color="black", font=("Arial", 12, "bold")).pack(side="left")
        self.lbl_pdf = ctk.CTkLabel(f_pdf, text="Nenhum PDF carregado", text_color="gray")
        self.lbl_pdf.pack(side="left", padx=15)
        self.vars['msg_pdf'] = self._caixa(height=80)

        # Seção 1 — Segurança
        self._secao("🛡️  SEGURANÇA")
        self._campo_num("Nº Ocorrências:", "num_ocorrencias", 0, ind_key="ind_seg")
        self.vars['desc_ocorrencia'] = self._caixa(placeholder="Descrição do acidente (se houver)...")

        # Seção 2 — Qualidade
        self._secao("⚙️  QUALIDADE")
        f_q = ctk.CTkFrame(self.scroll, fg_color="transparent")
        f_q.pack(fill="x", padx=20, pady=5)
        for label, chave, valor in [
            ("D1 (G)","d1_g","0"),("D1 (A)","d1_a","0"),
            ("FTT (G)","ftt_g","0"),("FTT (A)","ftt_a","0"),
            ("MVES (G)","mves_g","0"),("MVES (A)","mves_a","0"),
        ]:
            self._campo_indicador(f_q, label, chave, valor)
        self.vars['item_d1']   = self._caixa(placeholder="Item Foco D1...")
        self.vars['item_ftt']  = self._caixa(placeholder="Item Foco FTT...")
        self.vars['item_mves'] = self._caixa(placeholder="Item Foco MVES...")

        # Indicadores visuais de bandeira (tempo real)
        f_ind = ctk.CTkFrame(self.scroll, fg_color="transparent")
        f_ind.pack(fill="x", padx=30, pady=(5, 0))
        self.ind_labels = {}
        for k, txt in [("ind_seg","Seg"),("ind_d1","D1"),("ind_ftt","FTT"),
                       ("ind_mves","MVES"),("ind_prod","Prod"),("ind_5s","5S"),("ind_geral","GERAL")]:
            lbl = ctk.CTkLabel(f_ind, text=f"⚪ {txt}", font=("Segoe UI", 11, "bold"))
            lbl.pack(side="left", padx=8)
            self.ind_labels[k] = lbl

        # Seção 3 — Produção
        self._secao("📦 PRODUÇÃO")
        self._campo_num("Meta Ontem:", "prod_meta", 0)
        self._campo_num("Real Ontem:", "prod_real", 0)

        # Seção 4 — 5S
        self._secao("🧹 5S (ORGANIZAÇÃO)")
        self._campo_num("Nota 5S:", "nota_5s", 0)
        self.vars['desc_5s'] = self._caixa(placeholder="Itens e Responsáveis pelo 5S...")

        # Seção 4.5 — Liderança
        self._secao("💬 MENSAGEM DA LIDERANÇA (OPCIONAL)")
        self.vars['msg_lideranca'] = self._caixa(height=80,
            placeholder="Mensagem opcional do multifuncional para os colaboradores surdos...")

        # Seção 5 — Finalização
        self._secao("🎯 FINALIZAÇÃO")
        f_p = ctk.CTkFrame(self.scroll, fg_color="transparent")
        f_p.pack(fill="x", padx=30, pady=5)
        ctk.CTkLabel(f_p, text="Prioridade Geral:", width=150, anchor="w").pack(side="left")
        self.vars['prio'] = ctk.CTkComboBox(f_p, values=["SEGURANÇA","QUALIDADE","PRODUÇÃO","ORGANIZAÇÃO"],
                                            state="readonly", width=200)
        self.vars['prio'].set("SEGURANÇA")
        self.vars['prio'].pack(side="left", padx=10)
        ctk.CTkButton(f_p, text="🔄 Atualizar bandeiras", command=self._atualizar_indicadores,
                      fg_color="#607d8b", width=180).pack(side="left", padx=10)

        # Botões principais
        f_btns = ctk.CTkFrame(self.scroll, fg_color="transparent")
        f_btns.pack(pady=20)
        self.btn_otim = ctk.CTkButton(f_btns, text="🤖 OTIMIZAR (Ctrl+O)",
            command=self._otimizar_assincrono, fg_color="#673ab7", width=190)
        self.btn_otim.pack(side="left", padx=5)
        self.btn_prev = ctk.CTkButton(f_btns, text="👁️ PREVIEW (Ctrl+P)",
            command=self._preview_assincrono, fg_color="#2196f3", width=190)
        self.btn_prev.pack(side="left", padx=5)
        self.btn_save = ctk.CTkButton(f_btns, text="💾 SALVAR (Ctrl+S)",
            command=self._salvar_e_executar, fg_color="#4caf50", width=190)
        self.btn_save.pack(side="left", padx=5)
        self.btn_cancel = ctk.CTkButton(f_btns, text="⛔ Cancelar (Esc)",
            command=self._cancelar, fg_color="#9e9e9e", width=130, state="disabled")
        self.btn_cancel.pack(side="left", padx=5)

        # Preview
        ctk.CTkLabel(self.scroll, text="📋 PREVIEW (EDITÁVEL)",
                     font=("Segoe UI", 12, "bold"), text_color="#d32f2f").pack(anchor="w", padx=20, pady=(15, 2))
        self.preview = ctk.CTkTextbox(self.scroll, height=240, fg_color="#fffacd",
                                      text_color="#1a1a1a", font=("Courier New", 11))
        self.preview.pack(fill="x", padx=20, pady=(0, 20))

    def _criar_aba_voz(self, aba):
        """Tradutor de voz: ouve quem esta falando, transcreve o audio em
        texto e apresenta esse texto pro boneco de Libras sinalizar --
        util para uma conversa entre um ouvinte e uma pessoa surda."""
        ctk.CTkLabel(aba, text="🎤 TRADUTOR DE VOZ PARA LIBRAS",
                     font=("Segoe UI", 15, "bold"), text_color="#d32f2f").pack(anchor="w", padx=20, pady=(15, 2))
        ctk.CTkLabel(aba,
            text="Clique em Gravar, peça para a pessoa falar perto do microfone.\n"
                 "A fala vai sendo transcrita abaixo. Quando estiver pronto, clique em Apresentar.",
            justify="left", text_color="#555", font=("Segoe UI", 11)).pack(anchor="w", padx=20, pady=(0, 10))

        if not TEM_SPEECH_RECOGNITION:
            ctk.CTkLabel(aba,
                text="⚠️ Biblioteca de reconhecimento de voz não encontrada nesta instalação.\n"
                     "(pip install SpeechRecognition PyAudio)",
                text_color="#d32f2f", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=20, pady=10)

        f_btns_voz = ctk.CTkFrame(aba, fg_color="transparent")
        f_btns_voz.pack(pady=10)
        self.btn_gravar_voz = ctk.CTkButton(f_btns_voz, text="🎤 GRAVAR", command=self._iniciar_gravacao_voz,
            fg_color="#e53935", width=170, state="normal" if TEM_SPEECH_RECOGNITION else "disabled")
        self.btn_gravar_voz.pack(side="left", padx=5)
        self.btn_parar_voz = ctk.CTkButton(f_btns_voz, text="⏹️ PARAR", command=self._parar_gravacao_voz,
            fg_color="#9e9e9e", width=140, state="disabled")
        self.btn_parar_voz.pack(side="left", padx=5)
        self.btn_limpar_voz = ctk.CTkButton(f_btns_voz, text="🗑️ LIMPAR", command=self._limpar_texto_voz,
            fg_color="#607d8b", width=140)
        self.btn_limpar_voz.pack(side="left", padx=5)

        self.lbl_status_voz = ctk.CTkLabel(aba, text="Pronto para gravar.", text_color="#333", font=("Segoe UI", 11))
        self.lbl_status_voz.pack(pady=(0, 5))

        ctk.CTkLabel(aba, text="📝 TEXTO TRANSCRITO (EDITÁVEL)",
                     font=("Segoe UI", 12, "bold"), text_color="#d32f2f").pack(anchor="w", padx=20, pady=(10, 2))
        self.txt_voz = ctk.CTkTextbox(aba, height=300, fg_color="#fffacd",
                                       text_color="#1a1a1a", font=("Segoe UI", 12))
        self.txt_voz.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        self.btn_apresentar_voz = ctk.CTkButton(aba, text="🧑‍🤝‍🧑 APRESENTAR EM LIBRAS",
            command=self._apresentar_voz, fg_color="#4caf50", width=260, height=40,
            font=("Segoe UI", 12, "bold"))
        self.btn_apresentar_voz.pack(pady=(0, 15))

    def _secao(self, texto: str):
        ctk.CTkLabel(self.scroll, text=texto, font=("Segoe UI", 13, "bold"),
                     text_color="#d32f2f").pack(anchor="w", padx=20, pady=(15, 4))

    def _caixa(self, height=40, placeholder="") -> ctk.CTkTextbox:
        t = ctk.CTkTextbox(self.scroll, height=height, font=("Segoe UI", 11))
        t.pack(fill="x", padx=30, pady=2)
        if placeholder: t.insert("0.0", placeholder)
        return t

    def _campo_num(self, label, chave, valor_padrao, ind_key=None):
        f = ctk.CTkFrame(self.scroll, fg_color="transparent")
        f.pack(fill="x", padx=30, pady=2)
        ctk.CTkLabel(f, text=label, width=160, anchor="w").pack(side="left")
        e = ctk.CTkEntry(f, width=110); e.insert(0, str(valor_padrao)); e.pack(side="left")
        self.vars[chave] = e

    def _campo_indicador(self, pai, label, chave, valor_padrao):
        f = ctk.CTkFrame(pai, fg_color="transparent"); f.pack(side="left", padx=8)
        ctk.CTkLabel(f, text=label, font=("Arial", 10)).pack()
        e = ctk.CTkEntry(f, width=65); e.insert(0, valor_padrao); e.pack()
        self.vars[chave] = e

    # ------------------------------------------
    # STATUS / PROGRESSO
    # ------------------------------------------
    def _status(self, msg: str, cor: str = "#333"):
        self.lbl_status.configure(text=msg, text_color=cor)

    def _iniciar_progresso(self, msg: str):
        self._status(msg, "#1976d2")
        self.progresso.start()
        self.btn_cancel.configure(state="normal")
        CANCELAR_FLAG["valor"] = False

    def _parar_progresso(self, msg: str = "Pronto.", cor: str = "#2e7d32"):
        self.progresso.stop(); self.progresso.set(0)
        self._status(msg, cor)
        self.btn_cancel.configure(state="disabled")

    def _cancelar(self):
        if self.btn_cancel.cget("state") == "normal":
            CANCELAR_FLAG["valor"] = True
            self._status("⛔ Cancelando...", "#d32f2f")
            log.info("Usuário cancelou operação")

    # ------------------------------------------
    # HEALTHCHECK OLLAMA
    # ------------------------------------------
    def _verificar_ollama_inicial(self):
        def _check():
            ok, msg = ollama_online()
            self.after(0, lambda: self._atualizar_status_ia(ok, msg))
        threading.Thread(target=_check, daemon=True).start()

    def _atualizar_status_ia(self, ok: bool, msg: str):
        if ok:
            self.lbl_status_ia.configure(text=f"🟢 Ollama OK — modelo '{CONFIG['modelo_ia']}'", text_color="#c8e6c9")
        else:
            self.lbl_status_ia.configure(text=f"🔴 Ollama OFFLINE — {msg} (usando fallback)", text_color="#ffcdd2")
            log.warning(f"Ollama indisponível: {msg}")

    # ------------------------------------------
    # AUTOSAVE
    # ------------------------------------------
    def _coletar_bruto(self) -> dict:
        out = {}
        for k, w in self.vars.items():
            try:
                if isinstance(w, ctk.CTkTextbox):
                    out[k] = w.get("0.0", "end").rstrip("\n")
                elif isinstance(w, (ctk.CTkEntry, ctk.CTkComboBox)):
                    out[k] = w.get()
            except Exception:
                pass
        return out

    def _salvar_autosave(self):
        try:
            with open(CAMINHO_AUTOSAVE, "w", encoding="utf-8") as f:
                json.dump(self._coletar_bruto(), f, ensure_ascii=False)
        except Exception as e:
            log.warning(f"Autosave: {e}")

    def _autosave(self):
        self._salvar_autosave()
        self.after(CONFIG["autosave_segundos"] * 1000, self._autosave)

    def _restaurar_autosave(self):
        if not os.path.exists(CAMINHO_AUTOSAVE): return
        try:
            with open(CAMINHO_AUTOSAVE, "r", encoding="utf-8") as f:
                dados = json.load(f)
            for k, v in dados.items():
                if k in self.vars:
                    w = self.vars[k]
                    if isinstance(w, ctk.CTkTextbox):
                        w.delete("0.0", "end"); w.insert("0.0", v)
                    elif isinstance(w, ctk.CTkEntry):
                        w.delete(0, "end"); w.insert(0, v)
                    elif isinstance(w, ctk.CTkComboBox):
                        w.set(v)
            log.info("Autosave restaurado")
        except Exception as e:
            log.warning(f"Restauração autosave: {e}")

    # ------------------------------------------
    # COLETA / VALIDAÇÃO
    # ------------------------------------------
    def _texto(self, chave, placeholder=""):
        raw = self.vars[chave].get("0.0", "end").strip()
        return "" if raw == placeholder.strip() else raw

    def _coletar_dados(self):
        v = self.vars
        try:
            return {
                'msg_pdf': limpar_texto_campo(self._texto('msg_pdf'), 600),
                'desc_ocorrencia': limpar_texto_campo(self._texto('desc_ocorrencia',
                    "Descrição do acidente (se houver)..."), 400),
                'item_d1':   limpar_texto_campo(self._texto('item_d1',   "Item Foco D1..."), 100),
                'item_ftt':  limpar_texto_campo(self._texto('item_ftt',  "Item Foco FTT..."), 100),
                'item_mves': limpar_texto_campo(self._texto('item_mves', "Item Foco MVES..."), 100),
                'desc_5s':   limpar_texto_campo(self._texto('desc_5s',   "Itens e Responsáveis pelo 5S..."), 200),
                'prio': v['prio'].get(),
                'num_ocorrencias': int(float(v['num_ocorrencias'].get())),
                'd1_g': float(v['d1_g'].get()), 'd1_a': float(v['d1_a'].get()),
                'ftt_g': float(v['ftt_g'].get()),'ftt_a': float(v['ftt_a'].get()),
                'mves_g': float(v['mves_g'].get()),'mves_a': float(v['mves_a'].get()),
                'prod_meta': float(v['prod_meta'].get()),
                'prod_real': float(v['prod_real'].get()),
                'nota_5s':   float(v['nota_5s'].get()),
                'msg_lideranca': limpar_texto_campo(self._texto('msg_lideranca',
                    "Mensagem opcional do multifuncional para os colaboradores surdos..."), 400),
            }
        except ValueError:
            messagebox.showerror("Erro de Digitação",
                "Campos numéricos devem conter apenas números.\nExemplo correto: 97.9 (use ponto, não vírgula)")
            return None

    # ------------------------------------------
    # INDICADORES VISUAIS
    # ------------------------------------------
    def _atualizar_indicadores(self):
        dados = self._coletar_dados()
        if not dados: return
        b = calcular_bandeiras(dados)
        mapa = {"ind_seg":("Seg", b["seg"]),"ind_d1":("D1", b["d1"]),
                "ind_ftt":("FTT", b["ftt"]),"ind_mves":("MVES", b["mves"]),
                "ind_prod":("Prod", b["prod"]),"ind_5s":("5S", b["s5"]),
                "ind_geral":("GERAL", b["geral"])}
        for k, (txt, band) in mapa.items():
            emoji = "🟢" if band == "verde" else "🔴"
            self.ind_labels[k].configure(text=f"{emoji} {txt}")
        self._status(f"Bandeiras atualizadas — Geral: {b['geral'].upper()}",
                     "#2e7d32" if b['geral'] == "verde" else "#d32f2f")

    # ------------------------------------------
    # AÇÕES
    # ------------------------------------------
    def _carregar_pdf(self):
        arq = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf"), ("Todos", "*.*")])
        if not arq: return
        self._status("Lendo PDF...", "#1976d2")
        msg, dia = extrair_mensagem_pdf(arq)
        if msg:
            self.lbl_pdf.configure(text=f"✅ {dia}", text_color="green")
            self.vars['msg_pdf'].delete("0.0", "end")
            self.vars['msg_pdf'].insert("0.0", msg)
            self._status(f"PDF carregado: {dia}", "#2e7d32")
        else:
            self.lbl_pdf.configure(text="❌ Erro na leitura", text_color="red")
            self._status("Falha ao ler PDF", "#d32f2f")
            messagebox.showerror("Erro", "Não foi possível ler o PDF.")

    # --- OTIMIZAR (em lote — 1 chamada só) ---
    def _otimizar_assincrono(self):
        if self.btn_otim.cget("state") == "disabled": return
        self.btn_otim.configure(state="disabled", text="⏳ Otimizando...")
        self._iniciar_progresso("Otimizando campos via IA...")
        self.thread_atual = threading.Thread(target=self._thread_otimizar_lote, daemon=True)
        self.thread_atual.start()

    def _thread_otimizar_lote(self):
        """Envia TODOS os campos em uma única requisição → muito mais rápido."""
        campos_specs = [
            ('msg_pdf',         '',                                                                                     400),
            ('desc_ocorrencia', 'Descrição do acidente (se houver)...',                                                  150),
            ('item_d1',         'Item Foco D1...',                                                                        80),
            ('item_ftt',        'Item Foco FTT...',                                                                       80),
            ('item_mves',       'Item Foco MVES...',                                                                      80),
            ('desc_5s',         'Itens e Responsáveis pelo 5S...',                                                       150),
            ('msg_lideranca',   'Mensagem opcional do multifuncional para os colaboradores surdos...',                   200),
        ]

        entrada = {}
        for chave, ph, max_c in campos_specs:
            t = self._texto(chave, ph)
            if len(t) > 5:
                entrada[chave] = limpar_texto_campo(t, max_c)

        if not entrada:
            self.after(0, self._finalizar_otimizacao, {}, "Nenhum campo para otimizar.")
            return

        system_prompt = (
            "Você reescreve textos para linguagem simples de LIBRAS. "
            "Para cada chave do JSON recebido, reescreva o valor em no máximo 2 frases curtas, "
            "sem jargões, sem explicações. Retorne EXCLUSIVAMENTE um JSON válido com as mesmas chaves "
            "e os valores reescritos. Nada além do JSON."
        )
        prompt = json.dumps(entrada, ensure_ascii=False)
        resposta = chamar_ia(prompt, system_prompt=system_prompt)

        otimizados = {}
        if resposta:
            try:
                # Extrai JSON da resposta (caso venha com texto extra)
                m = re.search(r'\{.*\}', resposta, re.DOTALL)
                if m:
                    otimizados = json.loads(m.group(0))
            except Exception as e:
                log.warning(f"Otimização lote falhou no parse: {e} — fazendo fallback campo a campo")
                # fallback: chama um a um
                for chave, txt in entrada.items():
                    if CANCELAR_FLAG["valor"]: break
                    r = chamar_ia(txt, system_prompt="Reescreva em LIBRAS simples, máx 2 frases. Apenas o texto.")
                    if r: otimizados[chave] = r

        msg_fim = f"✅ {len(otimizados)} campo(s) otimizado(s)" if otimizados else "⚠️ Nenhum campo retornado pela IA"
        self.after(0, self._finalizar_otimizacao, otimizados, msg_fim)

    def _finalizar_otimizacao(self, otimizados: dict, msg_status: str):
        for chave, texto in otimizados.items():
            if chave in self.vars and isinstance(self.vars[chave], ctk.CTkTextbox) and texto:
                self.vars[chave].delete("0.0", "end")
                self.vars[chave].insert("0.0", texto.strip())
        self.btn_otim.configure(state="normal", text="🤖 OTIMIZAR (Ctrl+O)")
        cor = "#2e7d32" if otimizados else "#f57c00"
        self._parar_progresso(msg_status, cor)

    # --- PREVIEW ---
    def _preview_assincrono(self):
        if self.btn_prev.cget("state") == "disabled": return
        dados = self._coletar_dados()
        if not dados: return
        self._atualizar_indicadores()
        self.btn_prev.configure(state="disabled", text="⏳ Processando IA...")
        self._iniciar_progresso("Gerando narração via IA...")
        self.thread_atual = threading.Thread(target=self._thread_preview, args=(dados,), daemon=True)
        self.thread_atual.start()

    def _thread_preview(self, dados: dict):
        try:
            json_dds = montar_json_dds(dados)
            log.info(f"Preview JSON: {json.dumps(json_dds, ensure_ascii=False)[:300]}...")
            texto = gerar_texto_via_ia(json_dds)
            self.after(0, self._exibir_preview, texto, True)
        except Exception as e:
            log.error(f"Preview: {e}\n{traceback.format_exc()}")
            self.after(0, self._exibir_preview, f"[ERRO] {e}", False)

    def _exibir_preview(self, texto: str, ok: bool):
        self.preview.delete("0.0", "end")
        self.preview.insert("0.0", texto)
        self.btn_prev.configure(state="normal", text="👁️ PREVIEW (Ctrl+P)")
        self._parar_progresso("✅ Preview gerado" if ok else "❌ Erro no preview",
                              "#2e7d32" if ok else "#d32f2f")

    # --- SALVAR E APRESENTAR ---
    def _salvar_e_executar(self):
        txt = self.preview.get("0.0", "end").strip()
        if len(txt) < 20:
            messagebox.showwarning("Aviso", "O preview está vazio.\nGere o preview antes de salvar.")
            return
        with open(CAMINHO_TXT, "w", encoding="utf-8") as f:
            f.write(txt)
        self._salvar_autosave()
        log.info(f"DDS salvo ({len(txt)} chars)")
        self._status("💾 Salvo. Abrindo apresentação...", "#2e7d32")
        messagebox.showinfo("✅ Salvo!", "DDS salvo!\nO navegador vai abrir e o boneco de Libras aparece sozinho.\n\nO primeiro carregamento do avatar pode levar até 40 segundos.")
        # Minimiza esta janela antes de abrir o navegador: se ela ficar por
        # cima ou "tapando" a janela do boneco, o Chrome/Edge trata a pagina
        # como oculta e PAUSA a animacao do avatar no meio da frase (era a
        # causa do boneco "cortar" o que estava falando).
        self.iconify()
        rodar_apresentacao_libras()

    # ------------------------------------------
    # TRADUTOR DE VOZ (fala do ouvinte -> texto -> boneco)
    # ------------------------------------------
    def _status_voz(self, msg: str, cor: str = "#333"):
        self.lbl_status_voz.configure(text=msg, text_color=cor)

    def _iniciar_gravacao_voz(self):
        if not TEM_SPEECH_RECOGNITION:
            messagebox.showerror("Erro", "Biblioteca de reconhecimento de voz não está instalada.")
            return
        if getattr(self, '_ouvindo_voz', False):
            return
        try:
            self._sr_recognizer = sr.Recognizer()
            self._sr_mic = sr.Microphone()
            with self._sr_mic as source:
                self._sr_recognizer.adjust_for_ambient_noise(source, duration=0.5)
        except Exception as e:
            log.error(f"Microfone: {e}")
            messagebox.showerror("Erro no microfone", f"Não foi possível acessar o microfone:\n{e}")
            return

        self._ouvindo_voz = True
        self.btn_gravar_voz.configure(state="disabled")
        self.btn_parar_voz.configure(state="normal")
        self._status_voz("🎤 Ouvindo... peça para a pessoa falar perto do microfone.", "#1976d2")
        log.info("Tradutor de voz: gravação iniciada")

        def callback(recognizer, audio):
            try:
                texto = recognizer.recognize_google(audio, language="pt-BR")
                if texto:
                    self.after(0, self._adicionar_texto_voz, texto)
            except sr.UnknownValueError:
                pass  # trecho sem fala reconhecível, ignora e continua ouvindo
            except sr.RequestError as e:
                log.error(f"Reconhecimento de voz (rede): {e}")
                self.after(0, self._status_voz, "❌ Falha de conexão no reconhecimento de voz.", "#d32f2f")

        self._parar_ouvindo = self._sr_recognizer.listen_in_background(
            self._sr_mic, callback, phrase_time_limit=8)

    def _parar_gravacao_voz(self):
        if not getattr(self, '_ouvindo_voz', False):
            return
        self._ouvindo_voz = False
        parar = getattr(self, '_parar_ouvindo', None)
        if parar:
            parar(wait_for_stop=False)
        self.btn_gravar_voz.configure(state="normal")
        self.btn_parar_voz.configure(state="disabled")
        self._status_voz("⏹️ Gravação parada.", "#333")
        log.info("Tradutor de voz: gravação parada")

    def _adicionar_texto_voz(self, texto: str):
        atual = self.txt_voz.get("0.0", "end").strip()
        novo = f"{atual} {texto}".strip() if atual else texto
        self.txt_voz.delete("0.0", "end")
        self.txt_voz.insert("0.0", novo)
        self._status_voz("🎤 Ouvindo... (texto atualizado)", "#1976d2")

    def _limpar_texto_voz(self):
        self.txt_voz.delete("0.0", "end")
        self._status_voz("Texto limpo. Pronto para gravar.", "#333")

    def _apresentar_voz(self):
        texto = self.txt_voz.get("0.0", "end").strip()
        if len(texto) < 3:
            messagebox.showwarning("Aviso", "Ainda não há texto transcrito para apresentar.")
            return
        if getattr(self, '_ouvindo_voz', False):
            self._parar_gravacao_voz()
        log.info(f"Tradutor de voz: apresentando ({len(texto)} chars)")
        self._status_voz("💬 Abrindo o boneco para apresentar...", "#2e7d32")
        # Ver comentario em _salvar_e_executar: minimizar evita que esta
        # janela tape a do boneco e faca o Chrome/Edge pausar a animacao.
        self.iconify()
        rodar_apresentacao_libras(texto)

def garantir_modelo_ollama():
    """Cria o modelo narrador-dds no Ollama se ainda não existir."""
    try:
        ok, _ = ollama_online()
        if ok:
            return  # modelo já existe
        # Tenta criar a partir do Modelfile embutido
        modelfile_path = resource_path("narrador-dds.MD")
        if os.path.exists(modelfile_path):
            import subprocess
            log.info("Criando modelo narrador-dds no Ollama...")
            subprocess.run(
                ["ollama", "create", CONFIG["modelo_ia"], "-f", modelfile_path],
                capture_output=True, timeout=120
            )
    except Exception as e:
        log.warning(f"Não foi possível criar modelo automaticamente: {e}")

# ==========================================
# 9. ENTRADA
# ==========================================
if __name__ == "__main__":
    try:
        garantir_modelo_ollama()
        DDSAppIA().mainloop()
    except Exception:
        with open(os.path.join(PASTA_ATUAL, "erro_log.txt"), "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())
        log.critical(traceback.format_exc())
        messagebox.showerror("Erro Fatal", f"Travou. Consulte erro_log.txt e dds_app.log")