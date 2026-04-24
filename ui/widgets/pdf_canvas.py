"""
atlas_viewer.ui.widgets.pdf_canvas
====================================
Canvas replacement using QPdfView for high-performance native rendering.
"""

from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtPdf import QPdfDocument
from PySide6.QtCore import Qt, Signal, QMargins

class PDFCanvas(QPdfView):
    """
    Wrapper around QPdfView. 
    Switches to Custom zoom mode to allow precise control.
    """
    wheel_zoom = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        # Initialize with high-quality settings
        self.setPageMode(QPdfView.PageMode.SinglePage)
        
        # In PySide6, the enum value for manual/user-defined zoom is 'Custom'
        # rather than 'Manual' as seen in some C++ Qt documentation.
        self.setZoomMode(QPdfView.ZoomMode.Custom)
        
        # UI Styling
        self.setStyleSheet("background-color: #2b2b2b; border: none;")
        
        # QPdfView.setDocumentMargins expects a QMargins object.
        self.setDocumentMargins(QMargins(20, 20, 20, 20))

    def display_page(self, *args):
        """Legacy compatibility stub."""
        pass

    def clear(self):
        self.setDocument(None)

    def set_zoom(self, percent: int):
        """Sets the zoom factor (100% = 1.0)."""
        # Ensure we are in Custom mode
        if self.zoomMode() != QPdfView.ZoomMode.Custom:
            self.setZoomMode(QPdfView.ZoomMode.Custom)
        self.setZoomFactor(percent / 100.0)

    def wheelEvent(self, event):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            self.wheel_zoom.emit(delta)
        else:
            super().wheelEvent(event)
