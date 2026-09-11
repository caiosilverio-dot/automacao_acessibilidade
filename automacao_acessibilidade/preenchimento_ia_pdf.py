import os
import sys
import requests
import json
import traceback
import threading
import time
import tempfile
import hashlib
import logging
from datetime import datetime
import re
import webbrowser

from flask import Flask, request, jsonify, send_from_directory

try:
    import fitz
    TEM_PYMUPDF = True
except ImportError:
    try:
        import PyPDF2
        TEM_PYMUPDF = False
    except ImportError:
        TEM_PYMUPDF = None

def resource_path(rel: str) -> str:
    """Retorna caminho do recurso (funciona no .exe e no .py)."""
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)



# ==========================================
# 1. CONFIGURAÇÕES, CAMINHOS E LOG
# ==========================================
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
        "d1_geral":   0.68,
        "d1_area":    0.45,
        "ftt_geral":  97.90,
        "ftt_area":   95.5,
        "mves_geral": 2.5,
        "mves_area":  0.5,
        "_5s_pular":  90
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
    d1_area   = t.get("d1_area",   0.45)
    ftt_area  = t.get("ftt_area",  95.5)
    mves_area = t.get("mves_area", 0.5)
    s5_min    = t.get("_5s_pular", 90)

    b_seg  = "verde" if dados['num_ocorrencias'] == 0 else "vermelha"
    b_d1   = "verde" if dados['d1_a']   <= d1_area   else "vermelha"
    b_ftt  = "verde" if dados['ftt_a']  >= ftt_area  else "vermelha"
    b_mves = "verde" if dados['mves_a'] <= mves_area else "vermelha"
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
def rodar_apresentacao_libras(texto_bruto=None) -> bool:
    """Gera as paginas HTML do boneco de Libras (resumo_dds_app.html e
    resumo_dds_boneco.html). Se texto_bruto vier vazio, le o dados_dds.txt
    (fluxo do DDS diario); se vier preenchido, apresenta esse texto direto
    (usado pelo tradutor de voz). Quem abre a pagina e o proprio navegador
    (a aba do formulario navega ate /apresentacao/) — nao o Python: abrir
    como aba nova via webbrowser.open() deixava essa aba nova sem foco em
    alguns navegadores, o que atrasa/atrapalha o clique automatico que pula
    a saudacao do avatar (o "Oi, sou Icaro...")."""
    if texto_bruto is None:
        if not os.path.exists(CAMINHO_TXT):
            log.warning("rodar_apresentacao_libras: arquivo de texto não encontrado.")
            return False
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
// Chegamos a tentar window.vlibras.stop() direto (sem esperar o botao
// "Pular" renderizar), mas na pratica isso so muda uma flag interna --
// a animacao da saudacao dentro do player Unity continua tocando ate o
// fim de qualquer jeito, entao o "Oi, sou Icaro..." aparecia inteiro do
// mesmo jeito. Clicar de verdade no botao "Pular" (o mesmo que a pessoa
// clicaria manualmente) e o que realmente interrompe a animacao.
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
if(despachado||tentativas>400){{clearInterval(esperaBotao);}}
}},100);
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
// Mantem o app "vivo" enquanto esta pagina (a apresentacao do boneco)
// estiver aberta -- mesmo esquema de heartbeat do formulario.
function enviarHeartbeat(){fetch('/api/heartbeat',{method:'POST'}).catch(function(){});}
enviarHeartbeat();
setInterval(enviarHeartbeat, 4000);
</script>
</body></html>"""
    with open(CAMINHO_HTML, "w", encoding="utf-8") as f:
        f.write(html_externo)
    return True

# ==========================================
# 8. SERVIDOR WEB (INTERFACE)
# ==========================================
WEB_DIR = resource_path("web")

app = Flask(__name__)

# Sem janela pra fechar (a interface e uma aba de navegador comum), o
# processo nao tinha como saber que o usuario "fechou o app" -- ficava
# rodando escondido pra sempre e travava o .exe pra copiar/mover. As paginas
# (formulario e apresentacao do boneco) mandam um "sinal de vida" a cada
# poucos segundos; se ele parar de chegar (aba fechada), o servidor se
# encerra sozinho pouco depois.
ULTIMO_HEARTBEAT = {"ts": time.time()}
HEARTBEAT_TIMEOUT_SEGUNDOS = 25

CAMPOS_OTIMIZAVEIS = {
    'msg_pdf': 400, 'desc_ocorrencia': 150, 'item_d1': 80,
    'item_ftt': 80, 'item_mves': 80, 'desc_5s': 150, 'msg_lideranca': 200,
}


def _float_br(v) -> float:
    """float() tolerante a vírgula decimal (ex: '5,0' -> 5.0), já que o
    teclado numérico do Windows em pt-BR digita vírgula."""
    if v is None or v == '':
        return 0.0
    return float(str(v).strip().replace(',', '.'))


def montar_dados_do_form(raw: dict):
    """Converte o payload bruto vindo do formulário web nos mesmos tipos que
    a lógica de negócio (calcular_bandeiras / montar_json_dds) espera."""
    try:
        return {
            'msg_pdf':          limpar_texto_campo(raw.get('msg_pdf', ''), 600),
            'desc_ocorrencia':  limpar_texto_campo(raw.get('desc_ocorrencia', ''), 400),
            'item_d1':          limpar_texto_campo(raw.get('item_d1', ''), 100),
            'item_ftt':         limpar_texto_campo(raw.get('item_ftt', ''), 100),
            'item_mves':        limpar_texto_campo(raw.get('item_mves', ''), 100),
            'desc_5s':          limpar_texto_campo(raw.get('desc_5s', ''), 200),
            'prio':             raw.get('prio') or 'SEGURANÇA',
            'num_ocorrencias':  int(_float_br(raw.get('num_ocorrencias', 0))),
            'd1_g':   _float_br(raw.get('d1_g', 0)),   'd1_a':   _float_br(raw.get('d1_a', 0)),
            'ftt_g':  _float_br(raw.get('ftt_g', 0)),  'ftt_a':  _float_br(raw.get('ftt_a', 0)),
            'mves_g': _float_br(raw.get('mves_g', 0)), 'mves_a': _float_br(raw.get('mves_a', 0)),
            'prod_meta': _float_br(raw.get('prod_meta', 0)),
            'prod_real': _float_br(raw.get('prod_real', 0)),
            'nota_5s':   _float_br(raw.get('nota_5s', 0)),
            'msg_lideranca': limpar_texto_campo(raw.get('msg_lideranca', ''), 400),
        }, None
    except (ValueError, TypeError):
        return None, "Campos numéricos devem conter apenas números (ponto ou vírgula). Exemplo: 97.9 ou 97,9"


def _num_seguro(raw: dict, chave: str) -> float:
    try:
        return _float_br(raw.get(chave, 0))
    except (TypeError, ValueError):
        return 0.0


def otimizar_campos_batch(entrada: dict) -> dict:
    """Reescreve os textos recebidos em linguagem simples de LIBRAS via IA
    (uma única chamada em lote — bem mais rápido que campo a campo)."""
    if not entrada:
        return {}
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
            m = re.search(r'\{.*\}', resposta, re.DOTALL)
            if m:
                otimizados = json.loads(m.group(0))
        except Exception as e:
            log.warning(f"Otimização lote falhou no parse: {e} — fazendo fallback campo a campo")
            for chave, txt in entrada.items():
                if CANCELAR_FLAG["valor"]:
                    break
                r = chamar_ia(txt, system_prompt="Reescreva em LIBRAS simples, máx 2 frases. Apenas o texto.")
                if r:
                    otimizados[chave] = r
    return otimizados


# ------------------------------------------
# ROTAS — PÁGINA E ESTÁTICOS
# ------------------------------------------
@app.get("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.get("/<path:nome>")
def estaticos(nome):
    return send_from_directory(WEB_DIR, nome)


@app.get("/apresentacao/")
def apresentacao():
    return send_from_directory(PASTA_ATUAL, "resumo_dds_app.html")


@app.get("/apresentacao/<path:nome>")
def apresentacao_asset(nome):
    return send_from_directory(PASTA_ATUAL, nome)


# ------------------------------------------
# ROTAS — API
# ------------------------------------------
@app.post("/api/heartbeat")
def api_heartbeat():
    ULTIMO_HEARTBEAT["ts"] = time.time()
    return jsonify({"ok": True})


@app.get("/api/status")
def api_status():
    ok, msg = ollama_online()
    return jsonify({"ok": ok, "mensagem": msg, "modelo": CONFIG["modelo_ia"]})


@app.get("/api/config")
def api_config():
    return jsonify({
        "thresholds": CONFIG.get("thresholds", {}),
        "autosave_segundos": CONFIG.get("autosave_segundos", 30),
    })


@app.get("/api/autosave")
def api_autosave_get():
    if not os.path.exists(CAMINHO_AUTOSAVE):
        return jsonify({})
    try:
        with open(CAMINHO_AUTOSAVE, "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    except Exception as e:
        log.warning(f"Restauração autosave: {e}")
        return jsonify({})


@app.post("/api/autosave")
def api_autosave_post():
    raw = request.get_json(force=True, silent=True) or {}
    try:
        with open(CAMINHO_AUTOSAVE, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False)
    except Exception as e:
        log.warning(f"Autosave: {e}")
    return jsonify({"ok": True})


@app.post("/api/bandeiras")
def api_bandeiras():
    raw = request.get_json(force=True, silent=True) or {}
    dados = {
        'num_ocorrencias': int(_num_seguro(raw, 'num_ocorrencias')),
        'd1_a': _num_seguro(raw, 'd1_a'),
        'ftt_a': _num_seguro(raw, 'ftt_a'),
        'mves_a': _num_seguro(raw, 'mves_a'),
        'prod_real': _num_seguro(raw, 'prod_real'),
        'prod_meta': _num_seguro(raw, 'prod_meta'),
        'nota_5s': _num_seguro(raw, 'nota_5s'),
    }
    return jsonify(calcular_bandeiras(dados))


@app.post("/api/pdf")
def api_pdf():
    arquivo = request.files.get("arquivo")
    if not arquivo:
        return jsonify({"ok": False, "erro": "Nenhum arquivo enviado."}), 400
    fd, caminho = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        arquivo.save(caminho)
        msg, dia = extrair_mensagem_pdf(caminho)
    finally:
        try:
            os.remove(caminho)
        except OSError:
            pass
    if msg is None:
        return jsonify({"ok": False, "erro": "Não foi possível ler o PDF."}), 400
    return jsonify({"ok": True, "mensagem": msg, "dia": dia})


@app.post("/api/otimizar")
def api_otimizar():
    CANCELAR_FLAG["valor"] = False
    body = request.get_json(force=True, silent=True) or {}
    campos = body.get("campos", {})
    entrada = {}
    for chave, max_c in CAMPOS_OTIMIZAVEIS.items():
        t = (campos.get(chave) or "").strip()
        if len(t) > 5:
            entrada[chave] = limpar_texto_campo(t, max_c)

    if not entrada:
        return jsonify({"ok": True, "otimizados": {}, "mensagem": "Nenhum campo para otimizar."})

    otimizados = otimizar_campos_batch(entrada)
    msg = f"{len(otimizados)} campo(s) otimizado(s)" if otimizados else "Nenhum campo retornado pela IA"
    return jsonify({"ok": True, "otimizados": otimizados, "mensagem": msg})


@app.post("/api/preview")
def api_preview():
    CANCELAR_FLAG["valor"] = False
    raw = request.get_json(force=True, silent=True) or {}
    dados, erro = montar_dados_do_form(raw)
    if erro:
        return jsonify({"ok": False, "erro": erro}), 400
    try:
        json_dds = montar_json_dds(dados)
        log.info(f"Preview JSON: {json.dumps(json_dds, ensure_ascii=False)[:300]}...")
        texto = gerar_texto_via_ia(json_dds)
        return jsonify({"ok": True, "texto": texto, "bandeiras": calcular_bandeiras(dados)})
    except Exception as e:
        log.error(f"Preview: {e}\n{traceback.format_exc()}")
        return jsonify({"ok": False, "erro": str(e)}), 500


@app.post("/api/cancelar")
def api_cancelar():
    CANCELAR_FLAG["valor"] = True
    log.info("Usuário cancelou operação (web)")
    return jsonify({"ok": True})


@app.post("/api/salvar")
def api_salvar():
    body = request.get_json(force=True, silent=True) or {}
    texto = (body.get("texto") or "").strip()
    if len(texto) < 20:
        return jsonify({"ok": False, "erro": "O preview está vazio. Gere o preview antes de salvar."}), 400
    with open(CAMINHO_TXT, "w", encoding="utf-8") as f:
        f.write(texto)
    log.info(f"DDS salvo ({len(texto)} chars)")
    rodar_apresentacao_libras()
    return jsonify({"ok": True, "abrir": "/apresentacao/"})


@app.post("/api/apresentar_voz")
def api_apresentar_voz():
    body = request.get_json(force=True, silent=True) or {}
    texto = (body.get("texto") or "").strip()
    if len(texto) < 3:
        return jsonify({"ok": False, "erro": "Ainda não há texto transcrito para apresentar."}), 400
    log.info(f"Tradutor de voz: apresentando ({len(texto)} chars)")
    rodar_apresentacao_libras(texto)
    return jsonify({"ok": True, "abrir": "/apresentacao/"})

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
PORTA_WEB = 5057

def _abrir_navegador():
    time.sleep(1.2)
    webbrowser.open(f'http://127.0.0.1:{PORTA_WEB}')

def _vigiar_navegador_fechado():
    """Encerra o processo se nenhuma aba do app mandar heartbeat por um
    tempo (aba/navegador fechado) -- sem isso o app ficava rodando
    escondido pra sempre e travava o .exe pra copiar/mover."""
    ULTIMO_HEARTBEAT["ts"] = time.time()
    while True:
        time.sleep(3)
        if time.time() - ULTIMO_HEARTBEAT["ts"] > HEARTBEAT_TIMEOUT_SEGUNDOS:
            log.info("Nenhum sinal do navegador — encerrando aplicação.")
            os._exit(0)

if __name__ == "__main__":
    try:
        garantir_modelo_ollama()
        threading.Thread(target=_abrir_navegador, daemon=True).start()
        threading.Thread(target=_vigiar_navegador_fechado, daemon=True).start()
        app.run(host="127.0.0.1", port=PORTA_WEB, debug=False, use_reloader=False, threaded=True)
    except Exception:
        with open(os.path.join(PASTA_ATUAL, "erro_log.txt"), "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())
        log.critical(traceback.format_exc())
