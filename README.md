# 🆓 Atlas PDF Viewer — Free Edition v2.1.0

![Python](https://img.shields.io/badge/python-3.10+-blue)
![License](https://img.shields.io/badge/license-Free%20Edition-green)
![PySide6](https://img.shields.io/badge/PySide6-6.x-blueviolet)
![QtPdf](https://img.shields.io/badge/QtPdf-Engine-orange)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)
![Release](https://img.shields.io/badge/release-v2.1.0-brightgreen)
![Status](https://img.shields.io/badge/status-stable-success)
![Build](https://img.shields.io/badge/build-Nuitka%20%7C%20PyInstaller-blue)

Atlas PDF Viewer — Free Edition is a fast, lightweight, and offline-first desktop PDF reader designed for productivity-focused users. Built with PySide6 and powered by a native Qt PDF engine, it delivers smooth rendering, a clean interface, and zero bloat.

---

## 📂 Project Structure

atlas_opener_stripped/

├── main.py
├── core/
│   ├── __init__.py
│   ├── __pycache__/
│   ├── exceptions.py
│   ├── atlas_format.py
│   ├── mupdf_engine.py
│   ├── qtpdf_engine.py
│   ├── crypto_engine.py
│   ├── plugin_kernel.py
│   ├── document_engine.py
│   ├── engine_registry.py
│   ├── atlas_temp_manager.py
│   ├── compression_engine.py
│   ├── atlas_decrypt_worker.py
│   └── crypto_engine_legacy.py
├── services/
│   ├── __init__.py
│   ├── __pycache__/
│   ├── bookmark_service.py
│   ├── document_service.py
│   ├── thumbnail_service.py
│   └── attachment_service.py
├── models/
│   ├── __init__.py
│   └── __pycache__/
├── ui/
│   ├── __init__.py
│   ├── __pycache__/
│   ├── main_window.py
│   ├── tab_manager.py
│   ├── main_window_legacy.py
│   ├── dialogs/
│   │   ├── __init__.py
│   │   ├── __pycache__/
│   │   ├── base_dialog.py
│   │   ├── error_dialog.py
│   │   ├── info_dialogs.py
│   │   ├── mf_auth_dialog.py
│   │   ├── bookmarks_dialog.py
│   │   ├── attachments_dialog.py
│   │   ├── auth_error_handler.py
│   │   ├── documentation_dialog.py
│   │   └── mf_auth_dialog_legacy.py
│   └── widgets/
│       ├── toolbar.py
│       ├── __init__.py
│       ├── __pycache__/
│       ├── pdf_canvas.py
│       ├── search_panel.py
│       ├── pdf_viewer_tab.py
│       └── thumbnail_panel.py
├── utils/
│   ├── __init__.py
│   ├── __pycache__/
│   ├── path_utils.py
│   ├── ui_helpers.py
│   └── logging_setup.py
├── assets/
│   ├── icons/
│   └── Screenshots/
├── config/
│   ├── theme.py
│   ├── version.py
│   ├── __init__.py
│   ├── __pycache__/
│   ├── settings.py
│   └── logging_config.py
├── .idea/
├── .venv/
├── atlas_viewer.log
├── build_nuitka.bat
└── requirements.txt

---

## ⚡ Features (Free Edition)

### 📄 PDF Viewing
- Smooth and responsive PDF rendering  
- Fast page loading using QtPdf engine  
- Accurate text and layout display  

### 🗂️ Multi-Tab Workflow
- Open multiple PDFs  
- Fast tab switching  
- Clean document management  

### ⚡ Performance
- Lightweight architecture  
- Fast startup  
- Low memory usage  

### 🔌 Offline First
- 100% offline usage  
- No cloud dependency  
- Local file processing only  

### 🧩 Modular Architecture
- Plugin-ready system  
- Clean separation of components  
- Built for future expansion  

---

## 🛡️ Privacy

- No tracking  
- No telemetry  
- No internet required  
- Files never leave your device  

---

## 🖼 Screenshots

Main UI

![Main](assets/Screenshots/Main.png)

Multi Tab View

![Tabs](assets/Screenshots/Tab.png)

Upgrade to Pro

![Tabs](assets/Screenshots/Upgrade.png)

About UI

![Tabs](assets/Screenshots/About.png)

---

## 🚀 Installation

### Option 1 — Prebuilt

1. Download from Gumroad  
2. Extract ZIP  
3. Run executable  

---

### Option 2 — Source

git clone https://github.com/your-repo/Atlas-PDF-Viewer.git  
cd atlas-pdf-viewer  

python -m venv venv  
venv\Scripts\activate  

pip install -r requirements.txt  
python main.py  

---

## 🏗 Build

### PyInstaller

pyinstaller --onedir --noconsole --clean \
--name="AtlasPDFViewer" \
--icon="assets/icons/icon.ico" \
--add-data "assets;assets" \
main.py  

### Nuitka (Recommended)

  python -m nuitka ^
  --standalone ^
  --python-flag=no_asserts ^
  --python-flag=no_docstrings ^
  --windows-console-mode=disable ^
  --enable-plugin=pyside6 ^
  --include-module=PySide6.QtPdf ^
  --include-module=PySide6.QtPdfWidgets ^
  --include-module=atlas_core ^
  --include-qt-plugins=platforms,styles,imageformats ^
  --include-package=config ^
  --include-package=core ^
  --include-package=models ^
  --include-package=services ^
  --include-package=ui ^
  --include-package=utils ^
  --include-data-dir=assets=assets ^
  --follow-imports ^
  --nofollow-import-to=fitz ^
  --nofollow-import-to=pymupdf ^
  --nofollow-import-to=core.mupdf_engine ^
  --windows-icon-from-ico=assets/icons/icon.ico ^
  --windows-company-name="PatronHubDevs Technologies" ^
  --windows-product-name="ATLAS PDF Viewer" ^
  --windows-file-version=2.1.0.0 ^
  --windows-product-version=2.1.0.0 ^
  --windows-file-description="Commercial-Grade Multi-Format Document Viewer" ^
  --output-dir=dist ^
  --output-filename=Atlas_Viewer ^
  --jobs=4 ^
  main.py

---

## ⚠️ Limitations (Free Edition)

- No annotations  
- No editing tools  
- No encryption features  
- No ATLAS format support  (Open .atlas file and normal .pdf only)  

---

## 💎 Upgrade to Pro

- ATLAS encrypted document format  
- Rust-powered cryptographic engine  
- Advanced document features  
- Priority updates  

---

## 🧠 Built For

- Developers  
- Cybersecurity learners  
- Offline workflows  
- Productivity users  

---

## 📜 License

Free Edition — personal and commercial use allowed (with limitations)

---

## 👤 Author

Marco Polo  
PatronHubDevs Technologies  
Philippines  

---

## ⭐ Support

- Star the project  
- Share it  
- Upgrade to Pro  

---

## 🔥 Vision

Fast. Clean. Private. No compromises.
