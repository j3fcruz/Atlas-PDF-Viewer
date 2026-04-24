@echo off
REM ATLAS Opener — Nuitka onefile build script
REM Run from the atlas_opener\ directory with your venv activated.
REM
REM Requirements:
REM   pip install nuitka ordered-set zstandard
REM   pip install pyside6 pymupdf cryptography pyotp

python -m nuitka ^
  --onefile ^
  --standalone ^
  --output-filename=atlas_opener ^
  --output-dir=dist ^
  --windows-icon-from-ico=assets/icons/icon.ico ^
  --windows-product-name="ATLAS Opener" ^
  --windows-file-description="ATLAS Secure Document Opener" ^
  --enable-plugin=pyside6 ^
  --include-package=core ^
  --include-package=config ^
  --include-package=services ^
  --include-package=ui ^
  --include-package=models ^
  --include-package=utils ^
  --include-data-files=assets/icons/icon.ico=assets/icons/icon.ico ^
  --include-data-files=assets/icons/icon.png=assets/icons/icon.png ^
  --nofollow-import-to=services.print_manager ^
  --nofollow-import-to=services.print_spooler ^
  --nofollow-import-to=services.protection_service ^
  --nofollow-import-to=ui.widgets.sidebar ^
  --nofollow-import-to=ui.widgets.print_progress_dialog ^
  --nofollow-import-to=ui.widgets.print_queue_dialog ^
  --nofollow-import-to=ui.widgets.spooler_progress_dialog ^
  --nofollow-import-to=ui.widgets.print_worker ^
  --nofollow-import-to=ui.dialogs.protection_dialogs ^
  --nofollow-import-to=ui.dialogs.keyfile_generator_dialog ^
  --nofollow-import-to=ui.dialogs.documentation_dialog ^
  main.py

echo.
echo Build complete. Output: dist\atlas_opener.exe
