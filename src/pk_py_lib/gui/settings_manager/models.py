"""
src/pk_py_lib/gui/settings_manager/models.py

Qt item models and simple view-models for the Settings Manager GUI.

- ProfilesListModel: list model for profiles (id, name, active marker, item_count)
- KeyValueTableModel: table model for profile key/value items with JSON string display

These models are intentionally lightweight and reusable; they do not perform
persistence. Use the controller to fetch/apply changes.

Note: Syntax validation was performed using Python's ast module per project rules.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

# Defensive import for PySide6 (keeps library importable in headless environments)
try:
    from PySide6.QtCore import QAbstractListModel, QAbstractTableModel, QModelIndex, Qt, QObject, QByteArray
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QWidget
    PYSIDE_AVAILABLE = True
except Exception:  # pragma: no cover
    PYSIDE_AVAILABLE = False

    class _Missing:
        def __getattr__(self, name):
            raise RuntimeError("PySide6 is required for GUI models")

    QAbstractListModel = QAbstractTableModel = QModelIndex = Qt = QObject = QFont = QWidget = _Missing()  # type: ignore


@dataclass
class ProfileVM:
    """
    Simple view-model for a settings profile row.

    Attributes
    ----------
    id : str
        Profile UUID (text).
    name : str
        Profile display name (unique, CI).
    description : Optional[str]
        Optional description.
    is_active : bool
        Whether this profile is currently active.
    item_count : int
        Number of key/value items associated with the profile.
    created_at : str
        ISO8601Z created timestamp (text).
    updated_at : str
        ISO8601Z updated timestamp (text).

    Examples
    --------
    >>> d = {"id": "u", "name": "Default", "description": None, "is_active": True, "item_count": 0, "created_at": "t", "updated_at": "t"}
    >>> vm = ProfileVM.from_dict(d)
    >>> vm.name
    'Default'
    """

    id: str
    name: str
    description: Optional[str]
    is_active: bool
    item_count: int
    created_at: str
    updated_at: str

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ProfileVM":
        return ProfileVM(
            id=str(d.get("id", "")),
            name=str(d.get("name", "")),
            description=d.get("description"),
            is_active=bool(d.get("is_active", False)),
            item_count=int(d.get("item_count", 0)),
            created_at=str(d.get("created_at", "")),
            updated_at=str(d.get("updated_at", "")),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "is_active": self.is_active,
            "item_count": int(self.item_count),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class ProfilesListModel(QAbstractListModel):  # type: ignore[misc]
    """
    Qt list model exposing a collection of ProfileVM rows.

    Roles
    -----
    - Qt.DisplayRole: str display "name" (with optional marker)
    - Qt.FontRole: bold font for active profiles
    - Qt.UserRole: full dictionary payload of the profile row
    - Qt.UserRole + 1: profile id
    - Qt.UserRole + 2: is_active bool
    - Qt.UserRole + 3: item_count int
    """

    ROLE_PROFILE_DICT = Qt.UserRole
    ROLE_PROFILE_ID = Qt.UserRole + 1
    ROLE_IS_ACTIVE = Qt.UserRole + 2
    ROLE_ITEM_COUNT = Qt.UserRole + 3

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._rows: List[ProfileVM] = []

    # Required QAbstractItemModel overrides
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # type: ignore[override]
        if parent and parent.isValid():
            return 0
        return len(self._rows)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:  # type: ignore[override]
        if not index.isValid():
            return None
        row = index.row()
        if row < 0 or row >= len(self._rows):
            return None
        p = self._rows[row]

        if role == Qt.DisplayRole:
            marker = " ★" if p.is_active else ""
            return f"{p.name}{marker}"
        if role == Qt.FontRole:
            if p.is_active:
                f = QFont()
                f.setBold(True)
                return f
            return None
        if role == self.ROLE_PROFILE_DICT:
            return p.to_dict()
        if role == self.ROLE_PROFILE_ID:
            return p.id
        if role == self.ROLE_IS_ACTIVE:
            return p.is_active
        if role == self.ROLE_ITEM_COUNT:
            return p.item_count
        return None

    def roleNames(self) -> dict[int, QByteArray]:  # type: ignore[override]
        names = super().roleNames()
        try:
            names[self.ROLE_PROFILE_DICT] = QByteArray(b"profile")
            names[self.ROLE_PROFILE_ID] = QByteArray(b"profile_id")
            names[self.ROLE_IS_ACTIVE] = QByteArray(b"is_active")
            names[self.ROLE_ITEM_COUNT] = QByteArray(b"item_count")
        except Exception:
            pass
        return names

    # Helpers
    def set_profiles(self, profiles: List[Dict[str, Any]]) -> None:
        """
        Replace model contents with a new set of profiles.
        """
        self.beginResetModel()
        self._rows = [ProfileVM.from_dict(d) for d in profiles]
        self.endResetModel()

    def profiles(self) -> List[ProfileVM]:
        """
        Return current profiles as view-models.
        """
        return list(self._rows)

    def index_of_id(self, profile_id: str) -> int:
        """
        Return the index of the profile with the given id, or -1.
        """
        for i, p in enumerate(self._rows):
            if p.id == profile_id:
                return i
        return -1

    def profile_at(self, row: int) -> Optional[ProfileVM]:
        """
        Return the ProfileVM at the given row, or None.
        """
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None


class KeyValueTableModel(QAbstractTableModel):  # type: ignore[misc]
    """
    Qt table model for key/value items of a profile.

    Columns:
    - 0: Key (str)
    - 1: Value (JSON string representation)
    - 2: Type (derived from Python type of the value)

    The model stores Python values internally and renders JSON strings for display.
    Editing is expected to be orchestrated by higher-level dialogs; this model
    does not provide in-place editing by default.
    """

    COL_KEY = 0
    COL_VALUE = 1
    COL_TYPE = 2

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._rows: List[Tuple[str, Any]] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # type: ignore[override]
        if parent and parent.isValid():
            return 0
        return len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # type: ignore[override]
        return 3

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole) -> Any:  # type: ignore[override]
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return ["Key", "Value", "Type"][section] if 0 <= section < 3 else ""
        return str(section + 1)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:  # type: ignore[override]
        if not index.isValid():
            return None
        r, c = index.row(), index.column()
        if r < 0 or r >= len(self._rows):
            return None
        key, value = self._rows[r]
        if role == Qt.DisplayRole:
            if c == self.COL_KEY:
                return key
            if c == self.COL_VALUE:
                # Render compact JSON string for readability
                try:
                    import json
                    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
                except Exception:
                    return str(value)
            if c == self.COL_TYPE:
                return type(value).__name__
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:  # type: ignore[override]
        if not index.isValid():
            return Qt.NoItemFlags
        # Read-only by default; editing is through external dialogs
        return Qt.ItemIsSelectable | Qt.ItemIsEnabled

    # Public API
    def set_items_from_dict(self, items: Dict[str, Any]) -> None:
        """
        Replace model content with the provided mapping (sorted by key).
        """
        rows = [(str(k), items[k]) for k in sorted(items.keys(), key=lambda s: s.lower())]
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize current rows to a dictionary (keys unique, last-write wins).
        """
        out: Dict[str, Any] = {}
        for k, v in self._rows:
            out[k] = v
        return out

    def add_item(self, key: str, value: Any) -> None:
        """
        Append or update an item by key.
        """
        # Update if exists (case-insensitive)
        for i, (k, _) in enumerate(self._rows):
            if k.lower() == key.lower():
                self._rows[i] = (key, value)
                self.dataChanged.emit(self.index(i, 0), self.index(i, self.columnCount() - 1))  # type: ignore[attr-defined]
                return
        self.beginInsertRows(QModelIndex(), len(self._rows), len(self._rows))
        self._rows.append((key, value))
        self.endInsertRows()

    def remove_keys(self, keys: List[str]) -> int:
        """
        Remove items whose keys (case-insensitive) are included in keys.

        Returns
        -------
        int
            Number of rows removed.
        """
        to_remove = {k.lower() for k in keys}
        if not to_remove:
            return 0
        removed = 0
        # Rebuild list preserving order
        self.beginResetModel()
        new_rows: List[Tuple[str, Any]] = []
        for k, v in self._rows:
            if k.lower() in to_remove:
                removed += 1
                continue
            new_rows.append((k, v))
        self._rows = new_rows
        self.endResetModel()
        return removed

    def get_row(self, row: int) -> Optional[Tuple[str, Any]]:
        """
        Get (key, value) at a given row if valid.
        """
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None