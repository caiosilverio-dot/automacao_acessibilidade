import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import os
import sys
import subprocess
import requests
import traceback
import multiprocessing # Adicionado para evitar clones infinitos no .exe

# ==========================================
# 1. GESTÃO DE CAMINHOS DINÂMICOS
# ==========================================
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

if getattr(sys, 'frozen', False):
    PASTA_ATUAL = os.path.dirname(sys.executable)
else:
    PASTA_ATUAL = os.path.dirname(os.path.abspath(__file__))

CAMINHO_TXT = os.path.join(PASTA_ATUAL, "dados_dds.txt")
CAMINHO_HTML = os.path.join(PASTA_ATUAL, "resumo_dds_app.html")

# ==========================================
# 2. CONFIGURAÇÕES TÉCNICAS E IA
# ==========================================
OLLAMA_URL = "http://localhost:11434/api/generate"
MODELO_IA = "hpe-libras"

THRESHOLDS = {
    'd1_geral': 0.68, 'd1_area': 0.45,
    'ftt_geral': 97.90, 'ftt_area': 95.5,
    'mves_geral': 2.5, 'mves_area': 0.5,
    '_5s_pular': 90
}

# ==========================================
# 3. MÓDULO DO AVATAR
# ==========================================
def rodar_apresentacao_libras():
    try:
        import webview
    except ImportError:
        messagebox.showerror("Erro", "Motor de navegação (pywebview) não encontrado.")
        return

    if not os.path.exists(CAMINHO_TXT):
        messagebox.showwarning("Aviso", "Arquivo de texto não encontrado. Gere o DDS primeiro.")
        return

    with open(CAMINHO_TXT, "r", encoding="utf-8") as f:
        texto_dds = f.read().replace("\n", ". ")

    html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <style>
        * {{ margin: 0; padding: 0; overflow: hidden; }}
        body {{ width: 100vw; height: 100vh; background-color: #e2e4e7; }}
        #texto-alvo {{ position: absolute; top: 0; left: 0; opacity: 0.01; font-size: 20px; }}
        [vw-access-button] {{ display: none !important; }}
        [vw], .vw-plugin-wrapper, [vw-plugin-wrapper] {{
            position: fixed !important; top: 0 !important; left: 0 !important;
            width: 100vw !important; height: 100vh !important;
            max-width: none !important; max-height: none !important;
            transform: none !important; z-index: 999999 !important; display: block !important;
        }}
        [vw] iframe {{ width: 100% !important; height: 100% !important; border: none !important; }}
        .vw-plugin-top-wrapper {{ display: none !important; }}
    </style>
</head>
<body>
    <div id="texto-alvo">{texto_dds}</div>
    <div vw class="enabled">
        <div vw-access-button class="active"></div>
        <div vw-plugin-wrapper><div class="vw-plugin-top-wrapper"></div></div>
    </div>
    <script src="https://vlibras.gov.br/app/vlibras-plugin.js"></script>
    <script>
        new window.VLibras.Widget('https://vlibras.gov.br/app');
        window.addEventListener('load', function() {{
            setTimeout(function() {{
                var btn = document.querySelector('[vw-access-button]');
                if (btn) btn.click();
                setTimeout(function() {{
                    const el = document.getElementById('texto-alvo');
                    var range = document.createRange();
                    range.selectNodeContents(el);
                    var sel = window.getSelection();
                    sel.removeAllRanges();
                    sel.addRange(range);
                    var ev = new MouseEvent('click', {{ bubbles: true, cancelable: true, view: window }});
                    el.dispatchEvent(ev);
                }}, 12000); 
            }}, 2000);
        }});
    </script>
</body>
</html>"""

    # Mantém o salvamento para histórico, mas o WebView usará o HTML direto da memória
    with open(CAMINHO_HTML, "w", encoding="utf-8") as file:
        file.write(html_content)

    # CORREÇÃO: Passar o HTML diretamente resolve bloqueios de CORS do arquivo local no .exe
    webview.create_window('HPE - DDS Acessibilidade', html=html_content, fullscreen=True, frameless=True)
    webview.start()

# ==========================================
# 4. INTERFACE DE PREENCHIMENTO
# ==========================================
class DDSAppIA:
    def __init__(self, root):
        self.root = root
        self.root.title("HPE - Preenchimento DDS Inteligente")
        self.root.geometry("950x950")
        self.vars = {}
        self.criar_interface()

    def criar_interface(self):
        header = tk.Frame(self.root, bg="#d32f2f", pady=10)
        header.pack(fill="x")
        tk.Label(header, text="📊 GESTÃO DDS ACESSÍVEL (IA + LIBRAS)", font=("Segoe UI", 16, "bold"), fg="white", bg="#d32f2f").pack()

        canvas = tk.Canvas(self.root)
        scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=canvas.yview)
        self.scroll_frame = ttk.Frame(canvas)
        self.scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.secao("1. SEGURANÇA")
        self.campo_num("Nº Ocorrências:", "num_ocorrencias", 0)
        self.campo_texto_ia("Descrição do Acidente:", "desc_ocorrencia")

        self.secao("2. QUALIDADE")
        f_qual = tk.Frame(self.scroll_frame); f_qual.pack(fill="x", padx=20)
        self.campo_indicador(f_qual, "D1 (G)", "d1_g", "0.68")
        self.campo_indicador(f_qual, "D1 (A)", "d1_a", "0.45")
        self.campo_indicador(f_qual, "FTT (G)", "ftt_g", "97.9")
        self.campo_indicador(f_qual, "FTT (A)", "ftt_a", "95.5")
        self.campo_indicador(f_qual, "MVES (G)", "mves_g", "2.2")
        self.campo_indicador(f_qual, "MVES (A)", "mves_a", "0.5")
        
        self.campo_texto_ia("Item Foco D1:", "item_d1")
        self.campo_texto_ia("Item Foco FTT:", "item_ftt")
        self.campo_texto_ia("Item Foco MVES:", "item_mves")

        self.secao("3. PRODUÇÃO E 5S")
        self.campo_num("Meta Ontem:", "prod_meta", 40)
        self.campo_num("Real Ontem:", "prod_real", 41)
        self.campo_num("Hoje Meta:", "prod_hoje", 41)
        self.campo_num("Nota 5S:", "nota_5s", 88)
        self.campo_texto_ia("Responsáveis e Itens 5S:", "desc_5s")

        self.secao("4. FINALIZAÇÃO")
        self.combo("Bandeira Geral:", "bandeira", ["Verde", "Vermelha"])
        self.combo("Prioridade:", "prio", ["SEGURANÇA", "QUALIDADE", "PRODUÇÃO", "ORGANIZAÇÃO"])

        btns = tk.Frame(self.scroll_frame); btns.pack(pady=20)
        tk.Button(btns, text="🤖 OTIMIZAR IA", command=self.otimizar_tudo_ia, bg="#673ab7", fg="white", width=20, font=("Arial", 9, "bold")).pack(side="left", padx=5)
        tk.Button(btns, text="👁️ PREVIEW", command=self.atualizar_preview, bg="#2196f3", fg="white", width=15).pack(side="left", padx=5)
        tk.Button(btns, text="💾 SALVAR E ABRIR", command=self.salvar_e_executar, bg="#4caf50", fg="white", width=20, font=("Arial", 9, "bold")).pack(side="left", padx=5)

        self.preview = scrolledtext.ScrolledText(self.scroll_frame, height=12, font=("Segoe UI", 10))
        self.preview.pack(fill="both", padx=20, pady=10)

    def secao(self, t): tk.Label(self.scroll_frame, text=t, font=("Segoe UI", 10, "bold"), fg="#d32f2f").pack(pady=10, anchor="w", padx=20)
    def campo_num(self, l, k, d): f = tk.Frame(self.scroll_frame); f.pack(fill="x", padx=40, pady=2); tk.Label(f, text=l, width=20, anchor="w").pack(side="left"); v = tk.DoubleVar(value=d); tk.Entry(f, textvariable=v, width=10).pack(side="left"); self.vars[k] = v
    def campo_indicador(self, m, l, k, d): f = tk.Frame(m); f.pack(side="left", padx=10); tk.Label(f, text=l, font=("Arial", 8)).pack(); v = tk.DoubleVar(value=d); tk.Entry(f, textvariable=v, width=8).pack(); self.vars[k] = v
    def campo_texto_ia(self, l, k): f = tk.Frame(self.scroll_frame); f.pack(fill="x", padx=40, pady=5); tk.Label(f, text=l, font=("Arial", 8, "italic")).pack(anchor="w"); t = tk.Text(f, height=2, width=80, font=("Segoe UI", 9)); t.pack(side="left"); self.vars[k] = t
    def combo(self, l, k, o): f = tk.Frame(self.scroll_frame); f.pack(fill="x", padx=40, pady=2); tk.Label(f, text=l, width=20, anchor="w").pack(side="left"); v = tk.StringVar(value=o[0]); ttk.Combobox(f, textvariable=v, values=o, state="readonly").pack(side="left"); self.vars[k] = v

    def otimizar_tudo_ia(self):
        campos = ['desc_ocorrencia', 'item_d1', 'item_ftt', 'item_mves', 'desc_5s']
        for c in campos:
            txt = self.vars[c].get("1.0", tk.END).strip()
            if len(txt) > 5:
                try:
                    r = requests.post(OLLAMA_URL, json={"model": MODELO_IA, "prompt": txt, "stream": False}, timeout=20)
                    if r.status_code == 200:
                        self.vars[c].delete("1.0", tk.END)
                        self.vars[c].insert("1.0", r.json().get("response", "").strip())
                except: pass
        messagebox.showinfo("IA", "Textos Otimizados!")

    def gerar_corpo_texto(self):
        v = self.vars
        d1_s = "Meta boa" if v['d1_g'].get() <= THRESHOLDS['d1_geral'] else "Meta ruim"
        ftt_s = "Meta boa" if v['ftt_g'].get() >= THRESHOLDS['ftt_geral'] else "Meta ruim"
        mves_s = "Meta boa" if v['mves_g'].get() <= THRESHOLDS['mves_geral'] else "Meta ruim"
        
        return f"""Bom dia. Reunião agora.
Segurança: {'Acidente zero.' if v['num_ocorrencias'].get() == 0 else 'Aviso: ' + v['desc_ocorrencia'].get("1.0", tk.END).strip()}
D1: Geral {v['d1_g'].get()}. {d1_s}. Foco: {v['item_d1'].get("1.0", tk.END).strip()}
FTT: Geral {v['ftt_g'].get()}%. {ftt_s}. Foco: {v['item_ftt'].get("1.0", tk.END).strip()}
MVES: Geral {v['mves_g'].get()}. {mves_s}. Foco: {v['item_mves'].get("1.0", tk.END).strip()}
Produção: Ontem {v['prod_real'].get()}. Meta {v['prod_meta'].get()}.
5S Nota: {v['nota_5s'].get()}%. {'Limpar chão.' if v['nota_5s'].get() != 90 else ''} {v['desc_5s'].get("1.0", tk.END).strip()}
Bandeira {v['bandeira'].get()}. Prioridade {v['prio'].get()}. Obrigado."""

    def atualizar_preview(self):
        self.preview.delete("1.0", tk.END)
        self.preview.insert("1.0", self.gerar_corpo_texto())

    def salvar_e_executar(self):
        self.atualizar_preview()
        with open(CAMINHO_TXT, "w", encoding="utf-8") as f:
            f.write(self.preview.get("1.0", tk.END).strip())
        
        # CORREÇÃO: Tratamento adequado para chamar o executável compilado sem duplicar o sys.argv
        if getattr(sys, 'frozen', False):
            subprocess.Popen([sys.executable, "--apresentacao"])
        else:
            subprocess.Popen([sys.executable, sys.argv[0], "--apresentacao"])

# ==========================================
# 5. CONTROLADOR DE INÍCIO
# ==========================================
if __name__ == "__main__":
    multiprocessing.freeze_support() # CORREÇÃO: Obrigatório para PyInstaller + Windows não entrar em loop infinito
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "--apresentacao":
            rodar_apresentacao_libras()
        else:
            root = tk.Tk()
            app = DDSAppIA(root)
            root.mainloop()
    except Exception:
        with open(os.path.join(PASTA_ATUAL, "erro_log.txt"), "w") as f:
            f.write(traceback.format_exc())
        messagebox.showerror("Erro Fatal", f"O programa travou. Verifique o arquivo erro_log.txt na pasta.")