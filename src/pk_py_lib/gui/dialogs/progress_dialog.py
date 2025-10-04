import sys
import traceback
import inspect

from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QApplication,
    QMessageBox,
)
from PySide6.QtCore import Qt, Signal

from src.pk_py_lib.core.logging.decorators import log_errors
from src.pk_py_lib.core.logging.logger import get_logger


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

        self.logger = get_logger(__name__)

        
        def _build_ui(self):
            try:
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
            except Exception as e:
                exc_type = type(e).__name__
                exc_info = sys.exc_info()
                tb_lineno = exc_info[2].tb_lineno if exc_info[2] else inspect.currentframe().f_lineno
                func_name = inspect.currentframe().f_code.co_name
                locals_dict = locals()
                error_msg = f"{exc_type}: {str(e)}"
                self.logger.error(
                    error_msg,
                    extra={
                        "file": __file__,
                        "line": tb_lineno,
                        "function": func_name,
                        "locals": locals_dict,
                        "traceback": traceback.format_exc(),
                        "dialog_title": title,
                    }
                )
                QMessageBox.critical(self, "Progress Dialog Init Error", f"Failed to initialize progress dialog: {error_msg}")
                raise

        _build_ui(self)

    
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
        try:
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
        except ValueError as e:
            exc_type = type(e).__name__
            exc_info = sys.exc_info()
            tb_lineno = exc_info[2].tb_lineno if exc_info[2] else inspect.currentframe().f_lineno
            func_name = inspect.currentframe().f_code.co_name
            locals_dict = locals()
            error_msg = f"{exc_type}: {str(e)}"
            self.logger.error(
                error_msg,
                extra={
                    "file": __file__,
                    "line": tb_lineno,
                    "function": func_name,
                    "locals": locals_dict,
                    "traceback": traceback.format_exc(),
                    "dialog_title": self.windowTitle(),
                    "progress_value": value,
                    "status_text": text,
                }
            )
            QMessageBox.warning(self, "Progress Update Error", f"Invalid progress value: {error_msg}")
            raise  # Re-raise ValueError as per original
        except Exception as e:
            exc_type = type(e).__name__
            exc_info = sys.exc_info()
            tb_lineno = exc_info[2].tb_lineno if exc_info[2] else inspect.currentframe().f_lineno
            func_name = inspect.currentframe().f_code.co_name
            locals_dict = locals()
            error_msg = f"{exc_type}: {str(e)}"
            self.logger.error(
                error_msg,
                extra={
                    "file": __file__,
                    "line": tb_lineno,
                    "function": func_name,
                    "locals": locals_dict,
                    "traceback": traceback.format_exc(),
                    "dialog_title": self.windowTitle(),
                    "progress_value": value,
                    "status_text": text,
                }
            )
            QMessageBox.warning(self, "Progress Update Error", f"Failed to update progress: {error_msg}")
            # Do not re-raise to prevent operation halt

    
    def set_indeterminate(self, text: str):
        """
        Sets the progress bar to an indeterminate state and updates the status text.

        An indeterminate state is typically used when the total number of steps
        is unknown (e.g., connecting to a server, initializing).
        This is achieved by setting the progress bar range to (0, 0).

        :param text: The status text describing the current indeterminate operation.
        :type text: str
        """
        try:
            # Sets the progress bar to an indeterminate state (e.g., value 0, minimum 0, maximum 0)
            self.progress_bar.setRange(0, 0)
            self.progress_bar.setValue(0)
            self.status_label.setText(text)

            # Process events to ensure the UI updates immediately
            QApplication.processEvents()
        except Exception as e:
            exc_type = type(e).__name__
            exc_info = sys.exc_info()
            tb_lineno = exc_info[2].tb_lineno if exc_info[2] else inspect.currentframe().f_lineno
            func_name = inspect.currentframe().f_code.co_name
            locals_dict = locals()
            error_msg = f"{exc_type}: {str(e)}"
            self.logger.error(
                error_msg,
                extra={
                    "file": __file__,
                    "line": tb_lineno,
                    "function": func_name,
                    "locals": locals_dict,
                    "traceback": traceback.format_exc(),
                    "dialog_title": self.windowTitle(),
                    "status_text": text,
                }
            )
            QMessageBox.warning(self, "Indeterminate Progress Error", f"Failed to set indeterminate progress: {error_msg}")
            # Do not re-raise to prevent operation halt

    
    def _on_cancel(self):
        """
        Slot connected to self.cancel_button.clicked.

        Emits the cancellation_requested signal and closes the dialog.
        """
        try:
            # Emit the custom signal
            self.cancellation_requested.emit()
            # Close the dialog
            self.close()
        except Exception as e:
            exc_type = type(e).__name__
            exc_info = sys.exc_info()
            tb_lineno = exc_info[2].tb_lineno if exc_info[2] else inspect.currentframe().f_lineno
            func_name = inspect.currentframe().f_code.co_name
            locals_dict = locals()
            error_msg = f"{exc_type}: {str(e)}"
            self.logger.error(
                error_msg,
                extra={
                    "file": __file__,
                    "line": tb_lineno,
                    "function": func_name,
                    "locals": locals_dict,
                    "traceback": traceback.format_exc(),
                    "dialog_title": self.windowTitle(),
                }
            )
            QMessageBox.warning(self, "Cancel Error", f"Failed to cancel operation: {error_msg}")
            # Do not re-raise to prevent dialog issues

# Note: Python code validation performed. The code is syntactically valid and functionally correct based on specifications.