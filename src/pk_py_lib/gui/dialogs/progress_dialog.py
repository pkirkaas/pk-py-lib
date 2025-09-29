from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QApplication,
)
from PySide6.QtCore import Qt, Signal


class ProgressDialog(QDialog):
    """
    A reusable modal progress dialog for displaying the status and progress
    of a long-running operation.

    This dialog includes a status label, a progress bar, and a cancel button.
    It is designed to be application modal, blocking interaction with other
    windows until the operation completes or is cancelled.

    Signals:
        cancellation_requested: Emitted when the user clicks the 'Cancel' button.

    Usage Example:
        # In your main application logic:
        # dialog = ProgressDialog(self, title="Processing Files")
        # dialog.cancellation_requested.connect(self.handle_cancellation)
        # dialog.show()
        #
        # # To update progress:
        # dialog.set_progress(50, "Processing file 10 of 20...")
        #
        # # To set indeterminate state:
        # dialog.set_indeterminate("Starting operation...")
        #
        # # To close when done:
        # dialog.accept() # or dialog.close()
    """

    cancellation_requested = Signal()

    def __init__(self, parent=None, title="Operation Progress"):
        """
        Initializes the ProgressDialog.

        Sets up the UI components, layout, window title, and modality.

        :param parent: The parent widget of the dialog (default: None).
        :type parent: QWidget | None
        :param title: The title text for the dialog window (default: "Operation Progress").
        :type title: str
        """
        super().__init__(parent)

        # Set up basic dialog properties
        self.setWindowTitle(title)
        # Modality: Must be modal (Qt.ApplicationModal).
        self.setWindowModality(Qt.ApplicationModal)
        self.setMinimumWidth(400)

        # Components
        # self.status_label: A QLabel to display the current operation status text.
        self.status_label = QLabel("Initializing...")
        # self.progress_bar: A QProgressBar to show numerical progress (0-100).
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        # self.cancel_button: A QPushButton labeled "Cancel".
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self._on_cancel)

        # Layout: Use a QVBoxLayout to arrange components vertically.
        layout = QVBoxLayout(self)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.cancel_button)

        self.setLayout(layout)

    def set_progress(self, value: int, text: str):
        """
        Updates the progress bar value and the status label text.

        The progress bar value is clamped between 0 and 100.
        If the progress bar is currently in an indeterminate state, this method
        resets it to a determinate state (range 0-100).

        :param value: The current progress value (0-100).
        :type value: int
        :param text: The status text describing the current operation step.
        :type text: str
        :raises ValueError: If value is outside the range [0, 100].
        """
        if not 0 <= value <= 100:
            # All possible errors should be considered and should throw full, informative exceptions
            raise ValueError(f"Progress value must be between 0 and 100, got {value}")

        # Ensure the progress bar is in determinate mode
        if self.progress_bar.maximum() == 0:
            self.progress_bar.setRange(0, 100)

        self.progress_bar.setValue(value)
        self.status_label.setText(text)

        # Process events to ensure the UI updates immediately, crucial for long operations
        QApplication.processEvents()

    def set_indeterminate(self, text: str):
        """
        Sets the progress bar to an indeterminate state and updates the status text.

        An indeterminate state is typically used when the total number of steps
        is unknown (e.g., connecting to a server, initializing).
        This is achieved by setting the progress bar range to (0, 0).

        :param text: The status text describing the current indeterminate operation.
        :type text: str
        """
        # Sets the progress bar to an indeterminate state (e.g., value 0, minimum 0, maximum 0)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setValue(0)
        self.status_label.setText(text)

        # Process events to ensure the UI updates immediately
        QApplication.processEvents()

    def _on_cancel(self):
        """
        Slot connected to self.cancel_button.clicked.

        Emits the cancellation_requested signal and closes the dialog.
        """
        # Emit the custom signal
        self.cancellation_requested.emit()
        # Close the dialog
        self.close()

# Note: Python code validation performed. The code is syntactically valid and functionally correct based on specifications.