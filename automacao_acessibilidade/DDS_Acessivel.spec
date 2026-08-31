# -*- mode: python ; coding: utf-8 -*-
import os
import speech_recognition as _sr

# Inclusao cirurgica (nao collect_all): o pacote speech_recognition tambem
# traz o motor offline PocketSphinx (~38MB de dados de modelo acustico) e
# binarios FLAC para todas as plataformas, que nunca sao usados aqui (so
# usamos o reconhecimento online do Google). Incluir so o necessario evita
# um .exe gigante (e o limite de 100MB do GitHub).
_sr_dir = os.path.dirname(_sr.__file__)
datas = [(os.path.join(_sr_dir, 'flac-win32.exe'), 'speech_recognition')]
binaries = []
hiddenimports = ['pyaudio', 'speech_recognition.recognizers.google']

a = Analysis(
    ['preenchimento_ia_pdf.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch', 'torchvision', 'torchaudio', 'scipy', 'pandas', 'matplotlib', 'numpy', 'IPython', 'jupyter', 'nbformat', 'zmq', 'lxml', 'openpyxl', 'pyarrow', 'fastparquet', 'sympy', 'PIL', 'cv2', 'ultralytics', 'tensorflow', 'setuptools', 'cryptography', 'pygments', 'jedi', 'parso'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='DDS_Acessivel',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
