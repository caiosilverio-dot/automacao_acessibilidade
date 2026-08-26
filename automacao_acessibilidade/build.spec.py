# -*- mode: python ; coding: utf-8 -*-
import os

PASTA = r"C:\Users\fa811254\OneDrive - HPE Automotores do Brasil Ltda\Área de Trabalho\automacao_acessibilidade"

block_cipher = None

a = Analysis(
    [os.path.join(PASTA, 'preenchimento_ia_pdf.py')],
    pathex=[PASTA],
    binaries=[],
    datas=[
        (os.path.join(PASTA, 'narrador-dds.MD'), '.'),
    ],
    hiddenimports=[
        'customtkinter',
        'fitz',
        'PyPDF2',
        'requests',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
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
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)