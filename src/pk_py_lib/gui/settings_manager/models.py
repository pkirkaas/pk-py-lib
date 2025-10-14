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

import inspect
import traceback

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

from ...gui.utils.messages import handle_gui_error, gui_error_handler
from ...core.logging import logger
from ...core.logging.decorators import log_errors


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
    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="ProfileVM")
    def from_dict(d: Dict[str, Any]) -> "ProfileVM":
        try:
            return ProfileVM(
                id=str(d.get("id", "")),
                name=str(d.get("name", "")),
                description=d.get("description"),
                is_active=bool(d.get("is_active", False)),
                item_count=int(d.get("item_count", 0)),
                created_at=str(d.get("created_at", "")),
                updated_at=str(d.get("updated_at", "")),
            )
        except Exception as e:
            logger.error(
                f"Error creating ProfileVM from dict: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="ProfileVM.from_dict",
                parameters={"d": d},
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                error=e,
                title="ProfileVM Creation Error",
                component_name="ProfileVM.from_dict"
            )
            raise

    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="ProfileVM")
    def to_dict(self) -> Dict[str, Any]:
        try:
            return {
                "id": self.id,
                "name": self.name,
                "description": self.description,
                "is_active": self.is_active,
                "item_count": int(self.item_count),
                "created_at": self.created_at,
                "updated_at": self.updated_at,
            }
        except Exception as e:
            logger.error(
                f"Error converting ProfileVM to dict: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="ProfileVM.to_dict",
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                error=e,
                title="ProfileVM to Dict Error",
                component_name="ProfileVM.to_dict"
            )
            raise


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

    @log_errors(include_args=True, include_traceback=True)
    def __init__(self, parent: Optional[QObject] = None):
        try:
            super().__init__(parent)
            self._rows: List[ProfileVM] = []
        except Exception as e:
            logger.error(
                f"Error initializing ProfilesListModel: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="ProfilesListModel.__init__",
                parameters={"parent": parent},
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                error=e,
                title="Model Initialization Error",
                component_name="ProfilesListModel"
            )
            raise

    # Required QAbstractItemModel overrides
    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="ProfilesListModel")
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # type: ignore[override]
        try:
            if parent and parent.isValid():
                return 0
            return len(self._rows)
        except Exception as e:
            logger.error(
                f"Error in rowCount: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="rowCount",
                parameters={"parent": parent},
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                error=e,
                title="Row Count Error",
                component_name="ProfilesListModel.rowCount"
            )
            return 0

    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="ProfilesListModel")
    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:  # type: ignore[override]
        try:
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
        except Exception as e:
            logger.error(
                f"Error in data: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="data",
                parameters={"index": index, "role": role},
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                error=e,
                title="Data Access Error",
                component_name="ProfilesListModel.data",
                row=index.row() if index.isValid() else -1,
                role=role
            )
            return None

    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="ProfilesListModel")
    def roleNames(self) -> dict[int, QByteArray]:  # type: ignore[override]
        try:
            names = super().roleNames()
            names[self.ROLE_PROFILE_DICT] = QByteArray(b"profile")
            names[self.ROLE_PROFILE_ID] = QByteArray(b"profile_id")
            names[self.ROLE_IS_ACTIVE] = QByteArray(b"is_active")
            names[self.ROLE_ITEM_COUNT] = QByteArray(b"item_count")
            return names
        except Exception as e:
            logger.error(
                f"Error in roleNames: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="roleNames",
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                error=e,
                title="Role Names Error",
                component_name="ProfilesListModel.roleNames"
            )
            return super().roleNames()

    # Helpers
    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="ProfilesListModel")
    def set_profiles(self, profiles: List[Dict[str, Any]]) -> None:
        """
        Replace model contents with a new set of profiles.
        """
        try:
            self.beginResetModel()
            self._rows = [ProfileVM.from_dict(d) for d in profiles]
            self.endResetModel()
        except Exception as e:
            logger.error(
                f"Error setting profiles: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="set_profiles",
                parameters={"profiles_count": len(profiles)},
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                error=e,
                title="Set Profiles Error",
                component_name="ProfilesListModel.set_profiles",
                num_profiles=len(profiles)
            )
            # Reset model on error to avoid inconsistent state
            self.beginResetModel()
            self._rows = []
            self.endResetModel()

    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="ProfilesListModel")
    def profiles(self) -> List[ProfileVM]:
        """
        Return current profiles as view-models.
        """
        try:
            return list(self._rows)
        except Exception as e:
            logger.error(
                f"Error getting profiles: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="profiles",
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                error=e,
                title="Get Profiles Error",
                component_name="ProfilesListModel.profiles"
            )
            return []

    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="ProfilesListModel")
    def index_of_id(self, profile_id: str) -> int:
        """
        Return the index of the profile with the given id, or -1.
        """
        try:
            for i, p in enumerate(self._rows):
                if p.id == profile_id:
                    return i
            return -1
        except Exception as e:
            logger.error(
                f"Error finding index of id: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="index_of_id",
                parameters={"profile_id": profile_id},
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                error=e,
                title="Index Lookup Error",
                component_name="ProfilesListModel.index_of_id",
                profile_id=profile_id
            )
            return -1

    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="ProfilesListModel")
    def profile_at(self, row: int) -> Optional[ProfileVM]:
        """
        Return the ProfileVM at the given row, or None.
        """
        try:
            if 0 <= row < len(self._rows):
                return self._rows[row]
            return None
        except Exception as e:
            logger.error(
                f"Error getting profile at row: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="profile_at",
                parameters={"row": row},
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                error=e,
                title="Profile At Row Error",
                component_name="ProfilesListModel.profile_at",
                row=row
            )
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

    @log_errors(include_args=True, include_traceback=True)
    def __init__(self, parent: Optional[QObject] = None):
        try:
            super().__init__(parent)
            self._rows: List[Tuple[str, Any]] = []
        except Exception as e:
            logger.error(
                f"Error initializing KeyValueTableModel: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="KeyValueTableModel.__init__",
                parameters={"parent": parent},
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                error=e,
                title="Model Initialization Error",
                component_name="KeyValueTableModel"
            )
            raise

    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="KeyValueTableModel")
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # type: ignore[override]
        try:
            if parent and parent.isValid():
                return 0
            return len(self._rows)
        except Exception as e:
            logger.error(
                f"Error in rowCount: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="rowCount",
                parameters={"parent": parent},
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                error=e,
                title="Row Count Error",
                component_name="KeyValueTableModel.rowCount"
            )
            return 0

    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="KeyValueTableModel")
    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # type: ignore[override]
        try:
            return 3
        except Exception as e:
            logger.error(
                f"Error in columnCount: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="columnCount",
                parameters={"parent": parent},
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                error=e,
                title="Column Count Error",
                component_name="KeyValueTableModel.columnCount"
            )
            return 0

    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="KeyValueTableModel")
    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole) -> Any:  # type: ignore[override]
        try:
            if role != Qt.DisplayRole:
                return None
            if orientation == Qt.Horizontal:
                return ["Key", "Value", "Type"][section] if 0 <= section < 3 else ""
            return str(section + 1)
        except Exception as e:
            logger.error(
                f"Error in headerData: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="headerData",
                parameters={"section": section, "orientation": orientation, "role": role},
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                error=e,
                title="Header Data Error",
                component_name="KeyValueTableModel.headerData",
                section=section,
                role=role
            )
            return None

    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="KeyValueTableModel")
    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:  # type: ignore[override]
        try:
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
                    import json
                    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
                if c == self.COL_TYPE:
                    return type(value).__name__
            return None
        except json.JSONDecodeError as json_e:
            logger.warning(
                f"JSON rendering error in data: {type(json_e).__name__}: {json_e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="data",
                parameters={"index": index, "role": role, "value": value},
                stack_trace=traceback.format_exc()
            )
            return str(value)  # Fallback to string representation
        except Exception as e:
            logger.error(
                f"Error in data: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="data",
                parameters={"index": index, "role": role},
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                error=e,
                title="Data Access Error",
                component_name="KeyValueTableModel.data",
                row=r,
                column=c,
                role=role
            )
            return None

    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="KeyValueTableModel")
    def flags(self, index: QModelIndex) -> Qt.ItemFlags:  # type: ignore[override]
        try:
            if not index.isValid():
                return Qt.NoItemFlags
            # Read-only by default; editing is through external dialogs
            return Qt.ItemIsSelectable | Qt.ItemIsEnabled
        except Exception as e:
            logger.error(
                f"Error in flags: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="flags",
                parameters={"index": index},
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                error=e,
                title="Flags Error",
                component_name="KeyValueTableModel.flags"
            )
            return Qt.NoItemFlags

    # Public API
    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="KeyValueTableModel")
    def set_items_from_dict(self, items: Dict[str, Any]) -> None:
        """
        Replace model content with the provided mapping (sorted by key).
        """
        try:
            rows = [(str(k), items[k]) for k in sorted(items.keys(), key=lambda s: s.lower())]
            self.beginResetModel()
            self._rows = rows
            self.endResetModel()
        except Exception as e:
            logger.error(
                f"Error setting items from dict: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="set_items_from_dict",
                parameters={"items_count": len(items)},
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                error=e,
                title="Set Items Error",
                component_name="KeyValueTableModel.set_items_from_dict",
                num_items=len(items)
            )
            # Reset on error
            self.beginResetModel()
            self._rows = []
            self.endResetModel()

    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="KeyValueTableModel")
    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize current rows to a dictionary (keys unique, last-write wins).
        """
        try:
            out: Dict[str, Any] = {}
            for k, v in self._rows:
                out[k] = v
            return out
        except Exception as e:
            logger.error(
                f"Error converting to dict: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="to_dict",
                parameters={"rows_count": len(self._rows)},
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                error=e,
                title="To Dict Error",
                component_name="KeyValueTableModel.to_dict",
                num_rows=len(self._rows)
            )
            return {}

    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="KeyValueTableModel")
    def add_item(self, key: str, value: Any) -> None:
        """
        Append or update an item by key.
        """
        try:
            # Update if exists (case-insensitive)
            for i, (k, _) in enumerate(self._rows):
                if k.lower() == key.lower():
                    self._rows[i] = (key, value)
                    self.dataChanged.emit(self.index(i, 0), self.index(i, self.columnCount() - 1))  # type: ignore[attr-defined]
                    return
            self.beginInsertRows(QModelIndex(), len(self._rows), len(self._rows))
            self._rows.append((key, value))
            self.endInsertRows()
        except Exception as e:
            logger.error(
                f"Error adding item: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="add_item",
                parameters={"key": key},
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                error=e,
                title="Add Item Error",
                component_name="KeyValueTableModel.add_item",
                key=key
            )

    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="KeyValueTableModel")
    def remove_keys(self, keys: List[str]) -> int:
        """
        Remove items whose keys (case-insensitive) are included in keys.

        Returns
        -------
        int
            Number of rows removed.
        """
        try:
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
        except Exception as e:
            logger.error(
                f"Error removing keys: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="remove_keys",
                parameters={"keys_count": len(keys)},
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                error=e,
                title="Remove Keys Error",
                component_name="KeyValueTableModel.remove_keys",
                num_keys=len(keys)
            )
            return 0

    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="KeyValueTableModel")
    def get_row(self, row: int) -> Optional[Tuple[str, Any]]:
        """
        Get (key, value) at a given row if valid.
        """
        try:
            if 0 <= row < len(self._rows):
                return self._rows[row]
            return None
        except Exception as e:
            logger.error(
                f"Error getting row: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="get_row",
                parameters={"row": row},
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                error=e,
                title="Get Row Error",
                component_name="KeyValueTableModel.get_row",
                row=row
            )
            return None
