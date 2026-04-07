from PyQt6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget


class TransferStatusWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 0)
        layout.setSpacing(4)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 12px; color: #c8d8ee; font-weight: 600;")

        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(20)
        self.progress_bar.setStyleSheet(
            """
            QProgressBar {
                background: #0f1926;
                border: 1px solid #27415f;
                border-radius: 4px;
                text-align: center;
                color: #f3f8ff;
            }
            QProgressBar::chunk {
                background: #1f6fb2;
                border-radius: 3px;
            }
            """
        )

        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)
        self.hide()

    def show_status(self, message: str, progress: int):
        self.show()
        self.status_label.setText(message)
        self.progress_bar.setValue(progress)

    def clear_status(self):
        self.hide()
        self.status_label.clear()
        self.progress_bar.setValue(0)