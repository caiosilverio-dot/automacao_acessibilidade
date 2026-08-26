# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['..\\preenchimento_ia_pdf.py'],
    pathex=[],
    binaries=[],
    datas=[('C:\\Users\\fa811254\\OneDrive - HPE Automotores do Brasil Ltda\\Área de Trabalho\\automacao_acessibilidade\\narrador-dds.MD', '.')],
    hiddenimports=['customtkinter', 'fitz', 'PyPDF2', 'requests'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='HPE_MaoAmiga',
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
