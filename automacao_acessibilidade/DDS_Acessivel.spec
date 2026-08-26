# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['preenchimento_ia_pdf.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
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
