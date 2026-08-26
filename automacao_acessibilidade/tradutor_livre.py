import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import requests
import os
try:
    import webview
except ImportError:
    messagebox.showerror("Erro", "Instale o pywebview: pip install pywebview")
    exit()

# Configurações da IA
OLLAMA_URL = "http://localhost:11434/api/generate"
MODELO_IA = "hpe-libras"  # Usando o mesmo modelo que você treinou!

PASTA_BASE = r"C:\Users\fa811254\OneDrive - HPE Automotores do Brasil Ltda\Área de Trabalho\automacao_acessibilidade"
CAMINHO_HTML = os.path.join(PASTA_BASE, "traducao_avulsa.html")

class TradutorLivre:
    def __init__(self, root):
        self.root = root
        self.root.title("Tradutor Universal HPE -> Libras")
        self.root.geometry("800x600")
        self.criar_interface()

    def criar_interface(self):
        # Cabeçalho
        header = tk.Frame(self.root, bg="#673ab7", pady=10)
        header.pack(fill="x")
        tk.Label(header, text="🤟 TRADUTOR UNIVERSAL PARA LIBRAS (IA)", font=("Segoe UI", 16, "bold"), fg="white", bg="#673ab7").pack()

        # Texto Original
        tk.Label(self.root, text="1. Cole o texto normal em Português aqui:", font=("Segoe UI", 10, "bold")).pack(pady=(10,0), anchor="w", padx=20)
        self.txt_original = scrolledtext.ScrolledText(self.root, height=8, font=("Segoe UI", 10))
        self.txt_original.pack(fill="x", padx=20, pady=5)

        # Botão IA
        tk.Button(self.root, text="🤖 TRADUZIR / OTIMIZAR (IA)", command=self.traduzir_ia, bg="#2196f3", fg="white", font=("Segoe UI", 10, "bold"), pady=5).pack(pady=10)

        # Texto Otimizado
        tk.Label(self.root, text="2. Texto pronto para o Avatar (Pode editar se quiser):", font=("Segoe UI", 10, "bold")).pack(pady=(10,0), anchor="w", padx=20)
        self.txt_libras = scrolledtext.ScrolledText(self.root, height=8, font=("Segoe UI", 11, "bold"), fg="#d32f2f")
        self.txt_libras.pack(fill="x", padx=20, pady=5)

        # Botão Apresentar
        tk.Button(self.root, text="▶ ABRIR AVATAR EM TELA CHEIA", command=self.abrir_avatar, bg="#4caf50", fg="white", font=("Segoe UI", 12, "bold"), pady=10).pack(pady=15)

    def traduzir_ia(self):
        texto = self.txt_original.get("1.0", tk.END).strip()
        if not texto:
            messagebox.showwarning("Aviso", "Cole um texto primeiro!")
            return

        try:
            # Envia para o modelo HPE que você treinou
            response = requests.post(OLLAMA_URL, 
                                     json={"model": MODELO_IA, "prompt": texto, "stream": False},
                                     timeout=30)
            if response.status_code == 200:
                texto_ia = response.json().get("response", "").strip()
                self.txt_libras.delete("1.0", tk.END)
                self.txt_libras.insert("1.0", texto_ia)
            else:
                messagebox.showerror("Erro", "Erro ao processar na IA.")
        except Exception as e:
            messagebox.showerror("Erro de Conexão", f"Ollama está aberto?\n{e}")

    def gerar_html(self, texto_libras):
        # Trata quebras de linha para o HTML
        texto_html = texto_libras.replace("\n", ". ")
        
        # Cria um HTML limpo só com o boneco (similar ao do DDS, mas para textos avulsos)
        html = f"""<!DOCTYPE html>
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
    <div id="texto-alvo">{texto_html}</div>
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

                // Aguarda o boneco dar "oi" (12 segundos) e começa a traduzir
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
        with open(CAMINHO_HTML, "w", encoding="utf-8") as f:
            f.write(html)

    def abrir_avatar(self):
        texto = self.txt_libras.get("1.0", tk.END).strip()
        if len(texto) < 2:
            messagebox.showwarning("Aviso", "Não há texto traduzido para apresentar.")
            return
            
        self.gerar_html(texto)
        
        # Abre o PyWebView em tela cheia com o texto avulso
        webview.create_window('Avatar Libras - HPE', url=CAMINHO_HTML, fullscreen=True, frameless=True, background_color='#e2e4e7')
        webview.start()

if __name__ == "__main__":
    root = tk.Tk()
    app = TradutorLivre(root)
    root.mainloop()