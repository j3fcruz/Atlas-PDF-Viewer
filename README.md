<div align="center">

<img src="assets/icons/icon.ico" alt="Atlas PDF Viewer" width="96" height="96"/>

# Atlas PDF Viewer — Free Edition

**v2.1.0** · Built by [PatronHubDevs Technologies](https://github.com/your-repo) · 🇵🇭 Philippines

[![License: Free](https://img.shields.io/badge/License-Free%20Edition-blue.svg)](#-license)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://python.org)
[![PySide6](https://img.shields.io/badge/UI-PySide6-41CD52?logo=qt)](https://doc.qt.io/qtforpython/)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D4?logo=windows)](https://github.com/your-repo)
[![Offline](https://img.shields.io/badge/Offline-First-success)](#-privacy)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/your-repo/pulls)

> **Fast. Clean. Private. No compromises.**  
> A lightweight, offline-first desktop PDF reader engineered for productivity-focused users — zero telemetry, zero bloat.

[Download](#-installation) · [Screenshots](#-screenshots) · [Build from Source](#-build) · [Upgrade to Pro](#-upgrade-to-pro)

---

</div>

## Table of Contents

- [Overview](#-overview)
- [Features](#-features)
- [Screenshots](#-screenshots)
- [Project Structure](#-project-structure)
- [Installation](#-installation)
- [Build](#-build)
- [Limitations](#-limitations-free-edition)
- [Upgrade to Pro](#-upgrade-to-pro)
- [Privacy](#-privacy)
- [License](#-license)
- [Author](#-author)
- [Support](#-support)

---

## Overview

**Atlas PDF Viewer — Free Edition** is a fast, modular, and offline-first desktop PDF reader built with **PySide6** and powered by a native **Qt PDF engine**. Designed for developers, cybersecurity learners, and power users who demand clean tooling without cloud dependencies or background telemetry.

Engineered with a plugin-ready architecture and layered component design — built to scale into the Pro edition without refactoring.

---

## Features

### PDF Rendering
- Smooth, responsive PDF rendering via the QtPdf engine
- Accurate text and layout fidelity
- Fast page load with low memory overhead

### Multi-Tab Workflow
- Open and manage multiple PDFs simultaneously
- Instant tab switching with clean document state management

### Performance
- Lightweight architecture — minimal CPU/RAM footprint
- Fast cold-start, snappy UI interactions

### Offline First
- 100% local file processing — no network calls, ever
- No cloud sync, no remote storage, no external dependencies

### Modular Architecture
- Plugin-ready kernel (`plugin_kernel.py`)
- Engine registry pattern for swappable rendering backends
- Clean separation: UI / Services / Core / Utils

---

## Screenshots

| Main UI | Multi-Tab View |
|--------|----------------|
| ![Main UI](assets/screenshots/main.png) | ![Multi Tab](assets/screenshots/tab.png) |

| Upgrade to Pro | About |
|----------------|-------|
| ![Upgrade](assets/screenshots/upgrade.png) | ![About](assets/screenshots/about.png) |

---

## Project Structure

```
atlas_opener_stripped/
├── main.py                        # Entry point
├── core/
│   ├── __init__.py
│   ├── exceptions.py              # Custom exception hierarchy
│   ├── atlas_format.py            # ATLAS document format handler
│   ├── mupdf_engine.py            # MuPDF rendering backend
│   ├── qtpdf_engine.py            # QtPdf rendering backend (primary)
│   ├── crypto_engine.py           # Encryption/decryption engine (Pro)
│   ├── crypto_engine_legacy.py    # Legacy crypto compatibility layer
│   ├── plugin_kernel.py           # Plugin loader and lifecycle manager
│   ├── document_engine.py         # Core document abstraction
│   ├── engine_registry.py         # Backend engine registry/switcher
│   ├── atlas_temp_manager.py      # Secure temp file lifecycle
│   ├── compression_engine.py      # Document compression utilities
│   └── atlas_decrypt_worker.py    # Async decryption worker thread
├── services/
│   ├── bookmark_service.py        # Bookmark persistence and retrieval
│   ├── document_service.py        # Document open/close/state management
│   ├── thumbnail_service.py       # Async thumbnail generation
│   └── attachment_service.py      # Embedded attachment extraction
├── models/                        # Data models / DTOs
├── ui/
│   ├── main_window.py             # Primary application window
│   ├── tab_manager.py             # Tab lifecycle and switching
│   ├── dialogs/                   # Modal dialogs (about, upgrade, etc.)
│   └── widgets/                   # Reusable UI components
├── utils/                         # Shared utilities and helpers
├── assets/                        # Icons, images, stylesheets
├── config/                        # App configuration and settings
├── atlas_viewer.log               # Runtime log output
├── atlas_core.pyd                 # atlas_core compiled in RUST for better performance
├── build_nuitka.bat               # Nuitka production build script
└── requirements.txt               # Python dependencies
```

---

## Installation

### Option 1 — Prebuilt Binary (Recommended)

1. Download the latest release from [Gumroad](https://patronhubdevs.gumroad.com/l/nbuotr) or [GitHub Releases](https://github.com/j3fcruz/Atlas-PDF-Viewer/releases/tag/2.1.0)
2. Extract the ZIP archive
3. Run `Atlas_Viewer.exe`

> No Python installation required. Ships as a standalone executable.

### Option 2 — Run from Source

**Requirements:** Python 3.10+, Windows

```bash
# Clone the repository
git clone https://github.com/your-repo/Atlas-PDF-Viewer.git
cd Atlas-PDF-Viewer

# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Launch
python main.py
```

---

## Build

### PyInstaller

```bash
pyinstaller \
  --onedir \
  --noconsole \
  --clean \
  --name="AtlasPDFViewer" \
  --icon="assets/icons/icon.ico" \
  --add-data "assets;assets" \
  main.py
```

### Nuitka (Recommended for Production)

Produces faster, more compact, obfuscated binaries with better startup performance.

```bash
python -m nuitka \
  --standalone \
  --python-flag=no_asserts \
  --python-flag=no_docstrings \
  --windows-console-mode=disable \
  --enable-plugin=pyside6 \
  --include-module=PySide6.QtPdf \
  --include-module=PySide6.QtPdfWidgets \
  --include-package=config \
  --include-package=core \
  --include-package=models \
  --include-package=services \
  --include-package=ui \
  --include-package=utils \
  --include-data-dir=assets=assets \
  --follow-imports \
  --windows-icon-from-ico=assets/icons/icon.ico \
  --windows-company-name="PatronHubDevs Technologies" \
  --windows-product-name="ATLAS PDF Viewer" \
  --windows-file-version=2.1.0.0 \
  --windows-product-version=2.1.0.0 \
  --output-dir=dist \
  --output-filename=Atlas_Viewer \
  main.py
```

> Output: `dist/Atlas_Viewer.exe` — ready for distribution.

---

## Limitations (Free Edition)

| Feature | Free | Pro |
|--------|------|-----|
| PDF Viewing | ✅ | ✅ |
| Multi-Tab | ✅ | ✅ |
| Offline Operation | ✅ | ✅ |
| Annotations & Markup | ❌ | ✅ |
| Editing Tools | ❌ | ✅ |
| ATLAS Encrypted Format | ❌ | ✅ |
| Rust Crypto Engine | ❌ | ✅ |
| Advanced Document Features | ❌ | ✅ |
| Priority Updates | ❌ | ✅ |

---

## Upgrade to Pro

**Atlas PDF Viewer Pro** unlocks the full engine:

- **ATLAS Encrypted Document Format** — proprietary secure document container
- **Rust-Powered Cryptographic Engine** — high-performance, memory-safe encryption
- **Annotations & Editing Tools** — markup, highlights, and document editing
- **Advanced Document Features** — form filling, attachment management, bookmarks
- **Priority Updates & Support**

> [**Upgrade on Gumroad →**](https://patronhubdevs.gumroad.com/l/nbuotr)

---

## Privacy

Atlas PDF Viewer is engineered with a strict privacy-first architecture:

- **No telemetry** — zero usage data collected
- **No tracking** — no analytics, crash reporters, or fingerprinting
- **No internet required** — fully air-gap compatible
- **Files never leave your device** — all processing is local and in-memory

---

## License

**Free Edition** — Personal and commercial use permitted with the following limitations:

- Redistribution of modified builds is not permitted
- Pro features may not be reverse-engineered or bypassed
- Attribution to PatronHubDevs Technologies must be retained

See `LICENSE` for full terms.

---

## Author

**Marco Polo**  
PatronHubDevs Technologies  
🇵🇭 Philippines  
[GitHub](https://github.com/j3fcruz/Atlas-PDF-Viewer) · [Gumroad](https://patronhubdevs.gumroad.com/l/nbuotr)

---

## Support

If Atlas PDF Viewer has been useful to you:

- ⭐ **Star** the repository
- 📢 **Share** it with your network
- 💎 **[Upgrade to Pro](https://patronhubdevs.gumroad.com/l/nbuotr)** to support continued development

---

<div align="center">

**Atlas PDF Viewer** · PatronHubDevs Technologies · Philippines  
*Fast. Clean. Private. No compromises.*

</div>
