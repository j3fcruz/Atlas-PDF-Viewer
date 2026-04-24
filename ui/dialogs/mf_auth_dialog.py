# ── Standard Library ─────────────────────────────────────────
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── PySide6 Core ────────────────────────────────────────────
from PySide6.QtCore import Qt, Signal

# ── PySide6 Widgets ─────────────────────────────────────────
from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QWidget,
)

# ── ATLAS UI / Theme ────────────────────────────────────────
from config.theme import Colors, FontSize, Fonts, Spacing, Styles
from ui.dialogs.base_dialog import BaseDialog

# ── ATLAS Core ──────────────────────────────────────────────
from core.atlas_format import atlas_validate_path

# ── Security Dialog ─────────────────────────────────────────
from ui.dialogs.error_dialog import ErrorDialog


class MFAAuthDialog(BaseDialog):
    auth_complete = Signal(dict)

    _CONTEXT = "open_atlas"

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(parent, title="🔐  Identity Verification", width=540, height=460)

        self.factors: Dict[str, Any] = {}
        self.meta = meta or {}
        self._verifying = False

        self._build_ui()

    # ─────────────────────────────────────────────────────────
    # UI BUILD
    # ─────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.XL, Spacing.LG, Spacing.XL, Spacing.LG)
        root.setSpacing(Spacing.MD)

        root.addWidget(self.make_section_label("Verify Your Identity"))

        required: List[str] = self.meta.get("factors", [])
        if required:
            badge = QLabel(f"Required factors:  {',  '.join(f.upper() for f in required)}")
            badge.setFont(Fonts.default(FontSize.SM, bold=True))
            badge.setStyleSheet(
                f"color: {Colors.PRIMARY}; background: {Colors.PRIMARY_LIGHT}; "
                f"padding: 5px 10px; border-radius: 4px; font-weight: 600;"
            )
            root.addWidget(badge)

        root.addWidget(self.make_separator())

        # Password
        self._pwd_input: Optional[QLineEdit] = None
        if "password" in required:
            root.addWidget(QLabel("🔑  Password"))
            self._pwd_input = QLineEdit()
            self._pwd_input.setEchoMode(QLineEdit.EchoMode.Password)
            root.addWidget(self._pwd_input)

        # Keyfile
        self._kf_path_label: Optional[QLabel] = None
        if "keyfile" in required:
            kf_row = QHBoxLayout()
            btn = QPushButton("Browse…")
            btn.clicked.connect(self._select_keyfile)
            kf_row.addWidget(btn)

            self._kf_path_label = QLabel("No file selected")
            kf_row.addWidget(self._kf_path_label)
            kf_row.addStretch()

            root.addLayout(kf_row)

        # TOTP
        self._totp_input: Optional[QLineEdit] = None
        if "totp" in required:
            root.addWidget(QLabel("⏱️  TOTP Secret (Base32)"))
            self._totp_input = QLineEdit()
            root.addWidget(self._totp_input)

        root.addStretch()

        root.addLayout(self.make_button_row([
            ("✓  Verify & Open", "success", self._verify),
            ("Cancel", "danger", self.reject),
        ]))

    # ─────────────────────────────────────────────────────────
    # KEYFILE
    # ─────────────────────────────────────────────────────────
    def _select_keyfile(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Keyfile", "", "Key Files (*.key);;All Files (*)"
        )
        if not path:
            return

        try:
            atlas_validate_path(path, must_exist=True, must_be_file=True)

            validated_path = str(Path(path).resolve())
            self.factors["keyfile"] = validated_path

            assert self._kf_path_label is not None
            self._kf_path_label.setText(f"✓  {Path(path).name}")

        except Exception as exc:
            ErrorDialog.show_input_error(
                self, context=self._CONTEXT, factor="keyfile", exc=exc
            )
            self._clear_sensitive_inputs()

    # ─────────────────────────────────────────────────────────
    # VERIFY (FIXED FLOW)
    # ─────────────────────────────────────────────────────────
    def _verify(self) -> None:
        if self._verifying:
            return
        self._verifying = True

        required: List[str] = self.meta.get("factors", [])

        # Password
        if "password" in required:
            pwd = self._pwd_input.text() if self._pwd_input else ""
            if not pwd.strip():
                ErrorDialog.show_input_error(
                    self, context=self._CONTEXT, factor="password", exc=None
                )
                self._fail()
                return
            self.factors["password"] = pwd

        # Keyfile
        if "keyfile" in required:
            if "keyfile" not in self.factors:
                ErrorDialog.show_input_error(
                    self, context=self._CONTEXT, factor="keyfile", exc=None
                )
                self._fail()
                return

        # TOTP
        if "totp" in required:
            raw = (
                self._totp_input.text()
                .strip()
                .replace(" ", "")
                .replace("-", "")
                .upper()
                if self._totp_input else ""
            )

            if not raw:
                ErrorDialog.show_input_error(
                    self, context=self._CONTEXT, factor="totp", exc=None
                )
                self._fail()
                return

            try:
                import pyotp
                pyotp.TOTP(raw).now()
                self.factors["totp"] = raw
            except Exception as exc:
                ErrorDialog.show_input_error(
                    self, context=self._CONTEXT, factor="totp", exc=exc
                )
                self._fail()
                return

        # SUCCESS (single exit)
        self.auth_complete.emit(dict(self.factors))
        self.accept()

    # ─────────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────────
    def _fail(self) -> None:
        self._clear_sensitive_inputs()
        self._verifying = False

    def _clear_sensitive_inputs(self) -> None:
        if self._pwd_input:
            self._pwd_input.clear()
        if self._totp_input:
            self._totp_input.clear()