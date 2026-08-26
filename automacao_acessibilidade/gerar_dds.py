import os
import time

try:
    import webview
except ImportError:
    print("\nERRO: A biblioteca 'pywebview' não está instalada.")
    print("Abra o terminal/CMD e digite: pip install pywebview\n")
    exit()

def rodar_app_dds():
    pasta_base = r"C:\Users\fa811254\OneDrive - HPE Automotores do Brasil Ltda\Área de Trabalho\automacao_acessibilidade"
    caminho_txt = os.path.join(pasta_base, "dados_dds.txt")
    caminho_html = os.path.join(pasta_base, "resumo_dds.html")

    try:
        with open(caminho_txt, "r", encoding="utf-8") as file:
            # Texto limpo para facilitar a leitura do boneco
            texto_dds = file.read().replace("\n", " ").replace('"', "'")
    except FileNotFoundError:
        print(f"Erro: Arquivo não encontrado em:\n{caminho_txt}")
        return

    html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        /* Fundo total da tela (cor do VLibras para não dar contraste) */
        body, html {{ 
            width: 100vw; 
            height: 100vh; 
            background-color: #e2e4e7; 
            overflow: hidden; 
        }}

        /* Texto invisível para ser lido */
        #texto-alvo {{
            position: absolute;
            top: 0;
            left: 0;
            opacity: 0.01;
            font-size: 20px;
        }}

        /* FORÇANDO O BONECO A OCUPAR A TELA INTEIRA */
        [vw-access-button] {{ display: none !important; }}

        [vw], .vw-plugin-wrapper, [vw-plugin-wrapper] {{
            position: fixed !important;
            top: 0 !important;
            left: 0 !important;
            width: 100vw !important;
            height: 100vh !important;
            max-width: none !important;
            max-height: none !important;
            transform: none !important;
            z-index: 999999 !important;
            display: block !important;
        }}

        /* Estilo do Iframe (onde o boneco mora) */
        [vw] iframe {{
            width: 100% !important;
            height: 100% !important;
            border: none !important;
        }}

        /* Tenta esconder a barra azul de título do VLibras */
        .vw-plugin-top-wrapper {{ display: none !important; }}
    </style>
</head>
<body>
    <div id="texto-alvo">{texto_dds}</div>

    <div vw class="enabled">
        <div vw-access-button class="active"></div>
        <div vw-plugin-wrapper>
            <div class="vw-plugin-top-wrapper"></div>
        </div>
    </div>
    
    <script src="https://vlibras.gov.br/app/vlibras-plugin.js"></script>
    <script>
        // Inicia o widget
        var v = new window.VLibras.Widget('https://vlibras.gov.br/app');

        window.addEventListener('load', function() {{
            
            // 1. Abre o boneco após 2 segundos
            setTimeout(function() {{
                var btn = document.querySelector('[vw-access-button]');
                if (btn) btn.click();

                // 2. Aguarda 12 segundos (apresentação inicial)
                setTimeout(function() {{
                    const elementoTexto = document.getElementById('texto-alvo');
                    
                    // Função de leitura forçada
                    function forcarLeitura() {{
                        // Seleciona o texto
                        var range = document.createRange();
                        range.selectNodeContents(elementoTexto);
                        var sel = window.getSelection();
                        sel.removeAllRanges();
                        sel.addRange(range);
                        
                        // Simula clique de ativação no texto
                        var clickEvent = new MouseEvent('click', {{
                            bubbles: true,
                            cancelable: true,
                            view: window
                        }});
                        elementoTexto.dispatchEvent(clickEvent);
                    }}

                    // Executa a leitura
                    forcarLeitura();
                    
                    // Repete uma vez após 1 segundo para garantir
                    setTimeout(forcarLeitura, 1000);

                }}, 12000); 
            }}, 2000);
        }});
    </script>
</body>
</html>
"""

    with open(caminho_html, "w", encoding="utf-8") as file:
        file.write(html_content)
    
    print("Abrindo Aplicativo DDS em Tela Cheia...")
    print("Aperte ALT + F4 para fechar.")

    # Criando a janela do App
    window = webview.create_window(
        'HPE - DDS Acessibilidade', 
        url=caminho_html,
        fullscreen=True,
        frameless=True,
        background_color='#e2e4e7'
    )
    webview.start()

if __name__ == "__main__":
    rodar_app_dds()