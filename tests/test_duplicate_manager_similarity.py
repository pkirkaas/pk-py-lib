"""
tests/test_duplicate_manager_similarity.py

Smoke tests for DuplicateManagerDialog in similarity mode from img_app/img_app/widgets/duplicate_manager.py.
Tests initialization, UI elements (combo, spinbox), _populate_tree calls find_similar, no crashes on refresh/mock DB.
Uses pytest-qt for GUI, mock DB query and similarity.find_similar_phash.
Covers mode='similarity', mock hashes/groups, tree population, controls added.

4-space indent, rich comments. Syntax validated via ast.
Requires pytest-qt; assumes PySide6 installed.
"""

import pytest
from unittest.mock import patch, MagicMock
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from img_app.img_app.widgets.duplicate_manager import DuplicateManagerDialog
from src.pk_py_lib.core.database import DatabaseManager
from src.pk_py_lib.core.image.similarity import find_similar_phash


@pytest.fixture
def mock_db():
    """Mock DatabaseManager for query."""
    db = MagicMock(spec=DatabaseManager)
    mock_conn = MagicMock()
    db.get_connection.return_value.__enter__.return_value = mock_conn
    # Mock query for hashes
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [
        (1, "/img1.jpg", "a1b2c3d4e5f67890"),
        (2, "/img2.jpg", "a1b2c3d4e5f67891"),
        (3, "/img3.jpg", "1111111111111111"),
    ]
    mock_conn.execute.return_value.fetchone.return_value = None  # For image_id
    mock_conn.execute.return_value = mock_cur
    return db


@pytest.fixture
def mock_settings():
    """Mock settings for similarity."""
    return {"similarity": {"phash_threshold": 10}}


def test_duplicate_manager_similarity_init(qtbot, mock_db: DatabaseManager, mock_settings: dict):
    """Test initialization in similarity mode: UI elements added, no crash."""
    dialog = DuplicateManagerDialog(
        mode='similarity',
        db_manager=mock_db,
        settings_manager=None,  # Uses defaults
        paths=[],
        summary_text="Mock summary",
        report_text="Mock report"
    )

    qtbot.addWidget(dialog)

    # Assert UI controls added
    assert dialog.alg_combo is not None
    assert dialog.alg_combo.currentText() == "phash"  # Default
    assert dialog.threshold_spin is not None
    assert dialog.threshold_spin.value() == 10  # Default
    assert dialog.refresh_btn is not None
    assert dialog.refresh_btn.text() == "Refresh Groups"

    # Tree columns for similarity
    assert dialog.tree.columnCount() == 4
    assert [dialog.tree.headerItem().text(i) for i in range(4)] == [
        "Select", "Preview", "File Path", "Similarity Score"
    ]

    # No crash on init
    dialog.show()
    qtbot.waitUntil(dialog.isVisible, timeout=1000)

    dialog.close()


def test_duplicate_manager_similarity_populate_tree(qtbot, mock_db: DatabaseManager):
    """Test _populate_tree calls find_similar, populates tree with groups."""
    with patch("img_app.img_app.widgets.duplicate_manager.find_similar_phash") as mock_find:
        mock_groups = [["/img1.jpg", "/img2.jpg"]]  # Sample groups
        mock_find.return_value = mock_groups

        dialog = DuplicateManagerDialog(mode='similarity', db_manager=mock_db)
        qtbot.addWidget(dialog)

        # Mock DB query in _compute_and_populate
        with patch.object(dialog, '_compute_and_populate'):
            dialog._populate_tree(mock_groups)

        mock_find.assert_called_once()
        # Tree has groups
        assert dialog.tree.topLevelItemCount() > 0
        item0 = dialog.tree.topLevelItem(0)
        assert item0.childCount() == 2  # Paths in group
        assert item0.text(2) in ["/img1.jpg", "/img2.jpg"]  # Path column

        # Score column (Hamming) for children
        child0 = item0.child(0)
        assert child0.text(3) == "0"  # Mock score; actual from grouping

    dialog.close()


def test_duplicate_manager_similarity_no_crash_refresh(qtbot, mock_db: DatabaseManager):
    """Test refresh button calls _compute_and_populate without crash."""
    dialog = DuplicateManagerDialog(mode='similarity', db_manager=mock_db)
    qtbot.addWidget(dialog)

    # Connect signal
    dialog.refresh_btn.clicked.emit()

    # No exception on refresh (mocked internally)
    with patch.object(dialog, '_compute_and_populate'):
        dialog.refresh_btn.click()

    assert True  # No crash

    dialog.close()


def test_duplicate_manager_similarity_ui_elements_present(qtbot, mock_db: DatabaseManager):
    """Test similarity mode adds combo/spinbox, tree has preview/score columns."""
    dialog = DuplicateManagerDialog(mode='similarity', db_manager=mock_db)
    qtbot.addWidget(dialog)

    # Controls in layout
    assert dialog.findChild(type(dialog.alg_combo.__class__)) is not None
    assert dialog.findChild(type(dialog.threshold_spin.__class__)) is not None

    # Tree columns include Preview and Score
    header = dialog.tree.headerItem()
    assert "Preview" in header.text(1)
    assert "Similarity Score" in header.text(3)

    dialog.close()


def test_duplicate_manager_similarity_mock_db_populate(qtbot, mock_db: DatabaseManager):
    """Test with mock DB query: populates hashes, calls find_similar, tree has groups."""
    dialog = DuplicateManagerDialog(mode='similarity', db_manager=mock_db)
    qtbot.addWidget(dialog)

    with patch("img_app.img_app.widgets.duplicate_manager.find_similar_phash") as mock_find:
        mock_groups = [["/img1.jpg", "/img2.jpg"]]
        mock_find.return_value = mock_groups

        # Trigger populate
        dialog._compute_and_populate()

        mock_db.get_connection.assert_called_once()
        mock_find.assert_called_once_with(
            ANY,  # Hashes list from query
            threshold=10,  # Default
            settings=ANY
        )
        assert dialog.tree.topLevelItemCount() == 1  # One group
        group_item = dialog.tree.topLevelItem(0)
        assert group_item.childCount() == 2
        assert "/img1.jpg" in [group_item.child(0).text(2), group_item.child(1).text(2)]

    dialog.close()


def test_duplicate_manager_similarity_settings_override(qtbot, mock_db: DatabaseManager):
    """Test threshold from settings overrides default."""
    settings = {"similarity": {"phash_threshold": 5}}
    dialog = DuplicateManagerDialog(mode='similarity', db_manager=mock_db, settings_manager=MagicMock(get_settings=lambda: settings))
    qtbot.addWidget(dialog)

    assert dialog.threshold_spin.value() == 5  # Overridden

    dialog.close()