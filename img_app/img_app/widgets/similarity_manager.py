"""
img_app/img_app/widgets/similarity_manager.py

Dialog for managing perceptually similar images.

Inherits from BaseImageGroupManagerDialog and implements similarity-specific logic:
- Controls for selecting algorithm (phash, whash) and threshold.
- 'Compute Groups' functionality which queries the database and runs find_similar_images.
- Displays score range and average score.

Syntax validation: ast.parse verified.
"""

from __future__ import annotations

from typing import Optional, List, Dict
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QComboBox, QSpinBox, QPushButton, QMessageBox
from PySide6.QtCore import Qt

from src.pk_py_lib.core.logging import get_logger
from src.pk_py_lib.core.database import DatabaseManager
from src.pk_py_lib.core.image.similarity import find_similar_images
from src.pk_py_lib.gui.utils.messages import show_selectable_error
from pk_py_lib.gui.models import Group, ImageData
from img_app.img_app.widgets.base_group_manager import BaseImageGroupManagerDialog

# --- Logging Setup ---
LOGGER = get_logger("img_app.similarity")

class SimilarityManagerDialog(BaseImageGroupManagerDialog):
    """
    Dialog for managing perceptually similar images.
    """

    def __init__(
        self,
        groups: Optional[List[Group]] = None,
        db_manager: Optional[DatabaseManager] = None,
        settings: Optional[Dict[str, any]] = None,
        summary_text: str = "",
        report_text: str = "",
        parent: Optional[QWidget] = None
    ) -> None:
        """
        Initialize the Similarity Manager Dialog.

        Args:
            groups (Optional[List[Group]]): Initial groups of similar images.
            db_manager (Optional[DatabaseManager]): For hash queries.
            settings (Optional[Dict]): For default thresholds/algorithm.
            summary_text (str): Processing summary text.
            report_text (str): Report text detailing the similarity scan.
            parent (Optional[QWidget]): Parent widget.
        """
        self.db_manager = db_manager
        self.settings = settings or {}
        self.original_groups = groups or []
        
        # Pass the specific logger to the base class
        super().__init__(
            groups=groups,
            summary_text=summary_text,
            report_text=report_text,
            parent=parent,
            logger=LOGGER
        )
        
        # If no initial groups, attempt to compute them if DB is available
        if not self.groups and self.db_manager:
            self._compute_groups()

    def _setup_dialog_title(self) -> None:
        """Set the window title for the Similarity Manager."""
        self.setWindowTitle("Image Similarity Manager")

    def _get_report_tab_title(self) -> str:
        """Return the title for the report tab."""
        return "Similarity Report"

    def _setup_mode_specific_ui(self) -> None:
        """Ensure the Score column (column 6) is visible."""
        self.tree.setColumnHidden(6, False)

    def _setup_controls(self) -> QWidget:
        """
        Setup and return the top controls widget, including algorithm, threshold, and compute button.
        """
        controls_widget = QWidget()
        controls_layout = QHBoxLayout(controls_widget)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        
        controls_layout.addWidget(QLabel("Mode: Similarity (Perceptual)"))
        controls_layout.addStretch()

        # Algorithm and threshold controls
        controls_layout.addWidget(QLabel("Algorithm:"))
        self.alg_combo = QComboBox()
        self.alg_combo.addItems(["phash", "whash"])
        self.alg_combo.setCurrentText(self.settings.get("similarity", {}).get("algorithm", "phash"))
        controls_layout.addWidget(self.alg_combo)

        controls_layout.addWidget(QLabel("Threshold:"))
        # Default threshold from settings or 10
        default_threshold = self.settings.get("similarity", {}).get("phash_threshold", 10)
        self.threshold_spin = QSpinBox(minimum=0, maximum=64, value=default_threshold)
        controls_layout.addWidget(self.threshold_spin)

        self.compute_btn = QPushButton("Compute Groups")
        self.compute_btn.clicked.connect(self._compute_groups)
        controls_layout.addWidget(self.compute_btn)
        
        return controls_widget

    def _get_group_score_text(self, group: Group) -> tuple[str, str]:
        """
        Return the score text for a similarity group header.
        
        Args:
            group (Group): The image group data.
            
        Returns:
            tuple[str, str]: (score_range_text, avg_score_text)
        """
        min_s = f"{group.stats.min_score * 100:.1f}%"
        max_s = f"{group.stats.max_score * 100:.1f}%"
        score_range_text = f"{min_s} - {max_s}"
        avg_score_text = f"{group.stats.avg_score * 100:.1f}%"
        return score_range_text, avg_score_text

    def _get_image_score_text(self, img: ImageData) -> str:
        """
        Return the score text for a similar image child item.
        
        Args:
            img (ImageData): The image data object.
            
        Returns:
            str: The score text.
        """
        if img.score is not None:
            return f"{img.score * 100:.1f}%"
        return "N/A"

    # --- Similarity Specific Logic ---

    def _get_hashes_from_db(self, algorithm: str) -> List[Dict[str, str]]:
        """
        Query DB for hashes of given algorithm.

        Args:
            algorithm (str): 'phash', 'whash', 'blake3' etc.

        Returns:
            List[Dict[str, str]]: [{'path': str, 'hash': str}, ...]

        Raises:
            ValueError: No DB.
        """
        if not self.db_manager:
            raise ValueError("DB manager required for compute")
        conn = self.db_manager.get_connection()
        query = """
        SELECT im.absolute_path as path, ih.hash_value as hash
        FROM image_metadata im
        JOIN image_hashes ih ON im.id = ih.image_id
        WHERE ih.algorithm = ?
        """
        # Assuming the DB connection returns rows that can be accessed by attribute name (e.g., row.path)
        rows = conn.execute(query, (algorithm,)).fetchall()
        return [{'path': row.path, 'hash': row.hash} for row in rows if row.hash]

    def _compute_groups(self) -> None:
        """
        Compute groups for similarity mode.
    
        Queries DB hashes, calls find_similar_images, populates tree.
        """
        algorithm = self.alg_combo.currentText()
        threshold = self.threshold_spin.value()
    
        self.status_label.setText("Computing groups...")
        self.compute_btn.setEnabled(False)
        self.tree.setEnabled(False)
    
        try:
            hashes = self._get_hashes_from_db(algorithm)
            if not hashes:
                self.status_label.setText("No hashes found in DB.")
                return
    
            LOGGER.info(f"Input to find_similar_images: {len(hashes)} hash dicts, type List[Dict[str, str]]")
    
            # Note: find_similar_images is assumed to be synchronous for PoC as per original file comment
            self.groups = find_similar_images(hashes, algorithm, threshold, self.settings)
    
            if self.groups:
                LOGGER.info(f"Output from find_similar_images: {len(self.groups)} groups, first type {type(self.groups[0])}")
            else:
                LOGGER.info("Output from find_similar_images: empty list")
    
            self._populate_tree()
            # Post-populate synchronization: reflect current selections without clearing
            self._sync_tree_from_selections()
            if self.preview_table.rowCount() > 0:
                self._update_preview_checkboxes()
            self._update_status_line()
            self._update_delete_btn()
            LOGGER.info(f"Computed {len(self.groups)} groups (algorithm={algorithm}, threshold={threshold})")
    
        except Exception as e:
            LOGGER.error("Compute failed", exception=e)
            show_selectable_error(self, "Compute Error", f"Failed to compute groups: {str(e)}")
            self.status_label.setText("Compute failed.")
    
        finally:
            self.compute_btn.setEnabled(True)
            self.tree.setEnabled(True)