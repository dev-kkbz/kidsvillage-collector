# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — 키즈빌리지 상품 수집기 (single-file .exe)."""

a = Analysis(
    ['src/gui.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('config/settings.yaml', 'config'),
        ('templates/message_template.txt', 'templates'),
    ],
    hiddenimports=[
        'src',
        'src.resource',
        'src.config_loader',
        'src.image_manager',
        'src.message_builder',
        'src.models',
        'src.orchestrator',
        'src.scraper',
        'lxml._elementpath',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='KidsVillage_Collector',
    debug=False,
    strip=False,
    upx=True,
    console=False,
    icon=None,
)
