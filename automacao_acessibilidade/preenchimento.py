import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import os
import sys
import subprocess
import re
from datetime import datetime

# ==========================================
# THRESHOLDS ATUALIZADOS (HPE - DIRETRIZES)
# ==========================================
THRESHOLDS = {
    'd1_geral': 0.68,       # Dentro objetivo se <= 0.68
    'd1_area': 0.45,        # Bandeira Verde se <= 0.45
    'ftt_geral': 97.90,     # Dentro objetivo se >= 97.90
    'ftt_area': 95.5,       # Bandeira Verde se >= 95.5
    'mves_geral': 2.5,      # Dentro objetivo se <= 2.5
    'mves_area': 0.5,       # Bandeira Verde se <= 0.5
    '_5s_pular': 90         # Pular item se nota = 90
}

PASTA_BASE = r"C:\Users\fa811254\OneDrive - HPE Automotores do Brasil Ltda\Área de Trabalho\automacao_acessibilidade"
CAMINHO_TXT = os.path.join(PASTA_BASE, "dados_dds.txt")

class DDSApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Preenchimento Diário DDS - Modo Libras Profissional")
        self.root.geometry("900x900")

        self.vars = {}
        self.calcs = {
            'd1_g': "", 'd1_a': "",
            'ftt_g': "", 'ftt_a': "",
            'mves_g': "", 'mves_a': ""
        }

        self.criar_interface()

    def criar_interface(self):
        # Header
        header = tk.Frame(self.root, bg="#d32f2f", pady=15)
        header.pack(fill="x")
        tk.Label(header, text="📊 DDS HPE - LIBRAS DIRETA", font=("Segoe UI", 18, "bold"), fg="white", bg="#d32f2f").pack()
        tk.Label(header, text=datetime.now().strftime("%d/%m/%Y %H:%M"), fg="white", bg="#d32f2f").pack()

        # Scroll
        canvas = tk.Canvas(self.root)
        scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=canvas.yview)
        self.frame = ttk.Frame(canvas)
        self.frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0,0), window=self.frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # --- SEÇÕES ---
        self.secao("SEGURANÇA")
        self.campo("Ocorrências (Nº)", "num_ocorrencias", tk.IntVar(value=0))
        self.campo("O que aconteceu?", "desc_ocorrencia", tk.StringVar(value=""))

        self.secao("QUALIDADE D1 (<= 0.68 é bom)")
        self.campo("Geral", "d1_geral", tk.DoubleVar(value=0.68))
        self.campo("Área", "d1_area", tk.DoubleVar(value=0.45))
        self.campo("Item Foco", "item_qualidade", tk.StringVar(value="Limpador traseiro"))

        self.secao("FTT (>= 97.9 é bom)")
        self.campo("Geral %", "ftt_geral", tk.DoubleVar(value=97.90))
        self.campo("Área %", "ftt_area", tk.DoubleVar(value=95.5))
        self.campo("Item Foco", "item_ftt", tk.StringVar(value="Limpador traseiro"))

        self.secao("MVES (<= 2.5 é bom)")
        self.campo("Geral", "mves_geral", tk.DoubleVar(value=2.2))
        self.campo("Área", "mves_area", tk.DoubleVar(value=0.5))
        self.campo("Item Foco", "item_mves", tk.StringVar(value="Coluna teto amassada"))

        self.secao("PRODUÇÃO")
        self.campo("Ontem Meta", "prod_ontem_prog", tk.IntVar(value=40))
        self.campo("Ontem Real", "prod_ontem_real", tk.IntVar(value=41))
        self.campo("Hoje Meta", "prod_hoje_prog", tk.IntVar(value=41))

        self.secao("ORGANIZAÇÃO / 5S (90 pula item)")
        self.campo("Nota 5S %", "nota_5s", tk.IntVar(value=88))
        self.campo("Responsáveis Amanhã", "resp_5s", tk.StringVar(value="Marcos e Juliano"))

        self.secao("FINALIZAÇÃO")
        self.combo("Bandeira Geral", "bandeira_geral", ["Verde", "Vermelha"])
        self.combo("Prioridade", "prioridade_dia", ["SEGURANÇA", "QUALIDADE", "PRODUÇÃO", "ORGANIZAÇÃO"])

        # Botões
        btns = tk.Frame(self.frame)
        btns.pack(pady=20)
        tk.Button(btns, text="👁️ Gerar Texto", command=self.mostrar_preview, width=15, bg="#2196f3", fg="white").pack(side="left", padx=5)
        tk.Button(btns, text="💾 Salvar TXT", command=self.salvar_txt, width=15, bg="#4caf50", fg="white").pack(side="left", padx=5)
        tk.Button(btns, text="▶ Abrir Libras", command=self.abrir_apresentacao, width=15, bg="#d32f2f", fg="white").pack(side="left", padx=5)

        self.preview = scrolledtext.ScrolledText(self.frame, height=12, wrap=tk.WORD, font=("Segoe UI", 11))
        self.preview.pack(fill="both", padx=20, pady=20)

    def secao(self, titulo):
        tk.Label(self.frame, text=titulo, font=("Segoe UI", 11, "bold"), fg="#d32f2f").pack(pady=5)

    def campo(self, label, key, var):
        f = tk.Frame(self.frame); f.pack(fill="x", padx=20, pady=2)
        tk.Label(f, text=label, width=25, anchor="w").pack(side="left")
        tk.Entry(f, textvariable=var, width=35).pack(side="left")
        self.vars[key] = var

    def combo(self, label, key, options):
        f = tk.Frame(self.frame); f.pack(fill="x", padx=20, pady=2)
        tk.Label(f, text=label, width=25, anchor="w").pack(side="left")
        var = tk.StringVar(value=options[0])
        ttk.Combobox(f, textvariable=var, values=options, state="readonly", width=32).pack(side="left")
        self.vars[key] = var

    def calcular_logica_libras(self):
        v = self.vars
        # D1 e MVES (Menor melhor)
        self.calcs['d1_g'] = "Meta boa" if v['d1_geral'].get() <= THRESHOLDS['d1_geral'] else "Meta ruim"
        self.calcs['d1_a'] = "Bandeira Verde" if v['d1_area'].get() <= THRESHOLDS['d1_area'] else "Bandeira Vermelha"
        
        self.calcs['mves_g'] = "Meta boa" if v['mves_geral'].get() <= THRESHOLDS['mves_geral'] else "Meta ruim"
        self.calcs['mves_a'] = "Bandeira Verde" if v['mves_area'].get() <= THRESHOLDS['mves_area'] else "Bandeira Vermelha"
        
        # FTT (Maior melhor)
        self.calcs['ftt_g'] = "Meta boa" if v['ftt_geral'].get() >= THRESHOLDS['ftt_geral'] else "Meta ruim"
        self.calcs['ftt_a'] = "Bandeira Verde" if v['ftt_area'].get() >= THRESHOLDS['ftt_area'] else "Bandeira Vermelha"

    def gerar_texto_profissional(self):
        self.calcular_logica_libras()
        v = self.vars
        c = self.calcs
        
        texto = f"""Bom dia. Bom trabalho todos.
Reunião agora.

Segurança: {f'Acidente zero. Tudo bem.' if v['num_ocorrencias'].get() == 0 else f'Alerta. Acidente {v['num_ocorrencias'].get()}. {v['desc_ocorrencia'].get()}.'}

Qualidade D1:
Geral {v['d1_geral'].get()}. {c['d1_g']}.
Área {v['d1_area'].get()}. {c['d1_a']}.
Foco hoje: {v['item_qualidade'].get()}.

FTT:
Geral {v['ftt_geral'].get()}%. {c['ftt_g']}.
Área {v['ftt_area'].get()}%. {c['ftt_a']}.
{f'Foco hoje: {v['item_ftt'].get()}.' if 'Vermelha' in c['ftt_a'] else ''}

MVES:
Geral {v['mves_geral'].get()}. {c['mves_g']}.
Área {v['mves_area'].get()}. {c['mves_a']}.
{f'Foco hoje: {v['item_mves'].get()}.' if 'Vermelha' in c['mves_a'] else ''}

Produção:
Ontem meta {v['prod_ontem_prog'].get()}. Produção {v['prod_ontem_real'].get()}.
Hoje meta {v['prod_hoje_prog'].get()}.

Organização 5S:
Nota {v['nota_5s'].get()}%.
{'' if v['nota_5s'].get() == THRESHOLDS['_5s_pular'] else 'Problema: Peças chão. Limpar tudo. Amanhã 5S: ' + v['resp_5s'].get() + '.'}

Ferramentas:
Máquina problema? Não.
Etiquetas boas? Sim.
Vencimento olhar.

Ajuda precisa? Falar agora.

Hoje Bandeira {v['bandeira_geral'].get()}.
Prioridade {v['prioridade_dia'].get()}.
Obrigado."""
        return texto

    def mostrar_preview(self):
        t = self.gerar_texto_profissional()
        self.preview.delete(1.0, tk.END)
        self.preview.insert(tk.END, t)

    def salvar_txt(self):
        try:
            with open(CAMINHO_TXT, "w", encoding="utf-8") as f:
                f.write(self.gerar_texto_profissional())
            messagebox.showinfo("Sucesso", "Texto Libras salvo na pasta!")
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    def abrir_apresentacao(self):
        caminho_script = os.path.join(PASTA_BASE, "gerar_dds.py")
        if os.path.exists(caminho_script):
            subprocess.Popen([sys.executable, caminho_script], cwd=PASTA_BASE)
        else:
            messagebox.showerror("Erro", "Script 'gerar_dds.py' não encontrado.")

if __name__ == "__main__":
    root = tk.Tk()
    app = DDSApp(root)
    root.mainloop()