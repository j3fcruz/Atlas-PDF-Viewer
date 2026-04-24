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

# ── Security Dialog (CRITICAL) ───────────────────────────────
from ui.dialogs.error_dialog import ErrorDialog

# ─────────────────────────────────────────────────────────────────────────────
#  MFA AUTHENTICATION DIALOG
# ─────────────────────────────────────────────────────────────────────────────

class MFAAuthDialog(BaseDialog):
    """
    Multi-factor authentication dialog for opening .atlas files.

    Dynamically builds factor input fields based on the 'factors' list
    embedded in the ATLAS container metadata.

    Security posture
    ----------------
    All validation failures are routed through ErrorDialog.
    The user always sees "Authentication failed. Please try again."
    This prevents factor-enumeration by an attacker probing field-level errors.
    """

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
        self._build_ui()

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

        # ── Password ───────────────────────────────────────────────────────
        self._pwd_input: Optional[QLineEdit] = None
        if "password" in required:
            pw_lbl = QLabel("🔑  Password")
            pw_lbl.setFont(Fonts.default(FontSize.BASE, bold=True))
            root.addWidget(pw_lbl)
            self._pwd_input = QLineEdit()
            self._pwd_input.setEchoMode(QLineEdit.EchoMode.Password)
            self._pwd_input.setPlaceholderText("Enter your password")
            self._pwd_input.setFont(Fonts.default(FontSize.BASE))
            root.addWidget(self._pwd_input)
            root.addSpacing(Spacing.SM)

        # ── Key File ───────────────────────────────────────────────────────
        self._kf_path_label: Optional[QLabel] = None
        if "keyfile" in required:
            kf_lbl = QLabel("🗝️  Key File")
            kf_lbl.setFont(Fonts.default(FontSize.BASE, bold=True))
            root.addWidget(kf_lbl)
            kf_row = QHBoxLayout()
            kf_btn = QPushButton("Browse…")
            kf_btn.setFont(Fonts.default(FontSize.BASE))
            kf_btn.setStyleSheet(Styles.btn_primary())
            kf_btn.setFixedWidth(110)
            kf_btn.clicked.connect(self._select_keyfile)
            kf_row.addWidget(kf_btn)
            self._kf_path_label = QLabel("No file selected")
            self._kf_path_label.setFont(Fonts.default(FontSize.SM))
            self._kf_path_label.setStyleSheet(
                f"color: {Colors.TEXT_MUTED}; padding-left: 6px;"
            )
            kf_row.addWidget(self._kf_path_label)
            kf_row.addStretch()
            root.addLayout(kf_row)
            root.addSpacing(Spacing.SM)

        # ── TOTP ───────────────────────────────────────────────────────────
        self._totp_input: Optional[QLineEdit] = None
        if "totp" in required:
            totp_lbl = QLabel("⏱️  TOTP Secret (Base32)")
            totp_lbl.setFont(Fonts.default(FontSize.BASE, bold=True))
            root.addWidget(totp_lbl)
            hint = QLabel(
                "Enter the Base32 secret from your authenticator — NOT the 6-digit code."
            )
            hint.setFont(Fonts.default(FontSize.SM))
            hint.setStyleSheet(f"color: {Colors.WARNING}; padding: 2px 0;")
            hint.setWordWrap(True)
            root.addWidget(hint)
            self._totp_input = QLineEdit()
            self._totp_input.setPlaceholderText("e.g. JBSWY3DPEBLW64TMMQ======")
            self._totp_input.setFont(Fonts.mono(FontSize.SM))
            root.addWidget(self._totp_input)
            root.addSpacing(Spacing.SM)

        root.addStretch()
        root.addWidget(self.make_separator())

        root.addLayout(self.make_button_row([
            ("✓  Verify & Open", "success", self._verify),
            ("Cancel",           "danger",  self.reject),
        ]))

    # ── Slots ──────────────────────────────────────────────────────────────

    def _select_keyfile(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Keyfile", "", "Key Files (*.key);;All Files (*)"
        )
        if not path:
            return
        try:
            atlas_validate_path(path, must_exist=True, must_be_file=True)
            self.factors["keyfile"] = path
            assert self._kf_path_label is not None
            self._kf_path_label.setText(f"✓  {Path(path).name}")
            self._kf_path_label.setStyleSheet(
                f"color: {Colors.SUCCESS}; font-weight: 600; padding-left: 6px;"
            )
        except Exception as exc:
            ErrorDialog.input_validation_failure(
                self, context=self._CONTEXT, factor="keyfile", exc=exc
            )

    def _verify(self) -> None:
        required: List[str] = self.meta.get("factors", [])

        if "password" in required:
            pwd = self._pwd_input.text() if self._pwd_input else ""
            if not pwd.strip():
                ErrorDialog.input_validation_failure(
                    self, context=self._CONTEXT, factor="password"
                )
                return
            self.factors["password"] = pwd

        if "keyfile" in required and "keyfile" not in self.factors:
            ErrorDialog.input_validation_failure(
                self, context=self._CONTEXT, factor="keyfile"
            )
            return

        if "totp" in required:
            raw = (self._totp_input.text().strip() if self._totp_input else "")
            if not raw:
                ErrorDialog.input_validation_failure(
                    self, context=self._CONTEXT, factor="totp"
                )
                return
            try:
                import pyotp
                pyotp.TOTP(raw).now()
                self.factors["totp"] = raw
            except Exception as exc:
                ErrorDialog.input_validation_failure(
                    self, context=self._CONTEXT, factor="totp", exc=exc
                )
                return

        self.auth_complete.emit(self.factors)
        self.accept()
