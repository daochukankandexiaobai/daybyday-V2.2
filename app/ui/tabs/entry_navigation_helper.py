from __future__ import annotations

from typing import Callable

from app.utils.qt_compat import QEvent, QLineEdit, QModelIndex, QObject, QStyledItemDelegate, QTableWidget, Qt


class EntryNavigationDelegate(QStyledItemDelegate):
    def __init__(self, navigator: "EntryNavigationHelper", parent=None) -> None:
        super().__init__(parent)
        self.navigator = navigator

    def createEditor(self, parent, option, index: QModelIndex):  # noqa: ANN001
        editor = super().createEditor(parent, option, index)
        if editor is not None and index.isValid():
            self.navigator.register_editor(editor, int(index.row()), int(index.column()))
        return editor


class EntryNavigationHelper(QObject):
    """集中处理录入表格键盘导航（Enter/Tab/方向键）。"""

    def __init__(
        self,
        table: QTableWidget,
        is_editable_cell: Callable[[int, int], bool],
        data_row_count_getter: Callable[[], int],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.table = table
        self.is_editable_cell = is_editable_cell
        self.data_row_count_getter = data_row_count_getter
        self._editor_positions: dict[int, tuple[int, int]] = {}
        self._install()

    def build_delegate(self) -> EntryNavigationDelegate:
        return EntryNavigationDelegate(self, self.table)

    def _install(self) -> None:
        self.table.installEventFilter(self)
        self.table.viewport().installEventFilter(self)
        self.table.setTabKeyNavigation(False)

    def register_editor(self, editor, row: int, col: int) -> None:  # noqa: ANN001
        key = id(editor)
        self._editor_positions[key] = (row, col)
        editor.installEventFilter(self)
        editor.destroyed.connect(lambda *_: self._editor_positions.pop(key, None))

    def _editable_cells(self) -> list[tuple[int, int]]:
        rows = max(0, int(self.data_row_count_getter()))
        cols = self.table.columnCount()
        result: list[tuple[int, int]] = []
        for row in range(rows):
            for col in range(cols):
                if self.is_editable_cell(row, col):
                    result.append((row, col))
        return result

    def _next_cell(self, row: int, col: int) -> tuple[int, int] | None:
        cells = self._editable_cells()
        if not cells:
            return None
        try:
            idx = cells.index((row, col))
            return cells[(idx + 1) % len(cells)]
        except ValueError:
            return cells[0]

    def _prev_cell(self, row: int, col: int) -> tuple[int, int] | None:
        cells = self._editable_cells()
        if not cells:
            return None
        try:
            idx = cells.index((row, col))
            return cells[(idx - 1) % len(cells)]
        except ValueError:
            return cells[-1]

    def _next_in_col(self, row: int, col: int) -> tuple[int, int] | None:
        rows = max(0, int(self.data_row_count_getter()))
        for target in range(row + 1, rows):
            if self.is_editable_cell(target, col):
                return (target, col)
        return None

    def _prev_in_col(self, row: int, col: int) -> tuple[int, int] | None:
        for target in range(row - 1, -1, -1):
            if self.is_editable_cell(target, col):
                return (target, col)
        return None

    def _move_left(self, row: int, col: int) -> tuple[int, int] | None:
        for target in range(col - 1, -1, -1):
            if self.is_editable_cell(row, target):
                return (row, target)
        prev_cell = self._prev_cell(row, col)
        return prev_cell if prev_cell != (row, col) else None

    def _move_right(self, row: int, col: int) -> tuple[int, int] | None:
        cols = self.table.columnCount()
        for target in range(col + 1, cols):
            if self.is_editable_cell(row, target):
                return (row, target)
        next_cell = self._next_cell(row, col)
        return next_cell if next_cell != (row, col) else None

    def _apply_target(self, target: tuple[int, int] | None, start_edit: bool) -> bool:
        if target is None:
            return False
        row, col = target
        item = self.table.item(row, col)
        if item is None:
            return False
        self.table.setCurrentCell(row, col)
        self.table.scrollToItem(item)
        if start_edit:
            self.table.editItem(item)
        return True

    def _is_boundary_keep_editing(self, editor, key: int) -> bool:  # noqa: ANN001
        if not isinstance(editor, QLineEdit):
            return False
        if editor.hasSelectedText():
            return True
        text_len = len(editor.text())
        pos = int(editor.cursorPosition())
        if key == Qt.Key_Left:
            return pos > 0
        if key == Qt.Key_Right:
            return pos < text_len
        return False

    def _commit_editor_value(self, editor, row: int, col: int) -> None:  # noqa: ANN001
        if isinstance(editor, QLineEdit):
            item = self.table.item(row, col)
            if item is not None:
                item.setText(editor.text())

    def _handle_table_key(self, key: int, modifiers: int) -> bool:
        row = self.table.currentRow()
        col = self.table.currentColumn()
        if row < 0 or col < 0:
            return False
        if not self.is_editable_cell(row, col):
            target = self._next_cell(row, col)
            return self._apply_target(target, start_edit=False)

        shift = bool(modifiers & Qt.ShiftModifier)
        if key in (Qt.Key_Return, Qt.Key_Enter):
            if shift:
                target = self._prev_in_col(row, col) or self._prev_cell(row, col)
            else:
                target = self._next_in_col(row, col) or self._next_cell(row, col)
            return self._apply_target(target, start_edit=True)
        if key == Qt.Key_Tab and not shift:
            return self._apply_target(self._next_cell(row, col), start_edit=True)
        if key in (Qt.Key_Backtab,):
            return self._apply_target(self._prev_cell(row, col), start_edit=True)
        if key == Qt.Key_Tab and shift:
            return self._apply_target(self._prev_cell(row, col), start_edit=True)
        if key == Qt.Key_Up:
            return self._apply_target(self._prev_in_col(row, col), start_edit=False)
        if key == Qt.Key_Down:
            return self._apply_target(self._next_in_col(row, col), start_edit=False)
        if key == Qt.Key_Left:
            return self._apply_target(self._move_left(row, col), start_edit=False)
        if key == Qt.Key_Right:
            return self._apply_target(self._move_right(row, col), start_edit=False)
        return False

    def _handle_editor_key(self, editor, row: int, col: int, key: int, modifiers: int) -> bool:  # noqa: ANN001
        shift = bool(modifiers & Qt.ShiftModifier)

        if key in (Qt.Key_Left, Qt.Key_Right) and self._is_boundary_keep_editing(editor, key):
            return False

        if key in (Qt.Key_Return, Qt.Key_Enter):
            target = self._prev_in_col(row, col) if shift else self._next_in_col(row, col)
            if target is None:
                target = self._prev_cell(row, col) if shift else self._next_cell(row, col)
            self._commit_editor_value(editor, row, col)
            editor.clearFocus()
            self.table.setFocus()
            return self._apply_target(target, start_edit=True)

        if key == Qt.Key_Tab and not shift:
            self._commit_editor_value(editor, row, col)
            editor.clearFocus()
            self.table.setFocus()
            return self._apply_target(self._next_cell(row, col), start_edit=True)

        if key in (Qt.Key_Backtab,) or (key == Qt.Key_Tab and shift):
            self._commit_editor_value(editor, row, col)
            editor.clearFocus()
            self.table.setFocus()
            return self._apply_target(self._prev_cell(row, col), start_edit=True)

        if key == Qt.Key_Up:
            self._commit_editor_value(editor, row, col)
            editor.clearFocus()
            self.table.setFocus()
            return self._apply_target(self._prev_in_col(row, col), start_edit=True)

        if key == Qt.Key_Down:
            self._commit_editor_value(editor, row, col)
            editor.clearFocus()
            self.table.setFocus()
            return self._apply_target(self._next_in_col(row, col), start_edit=True)

        if key == Qt.Key_Left:
            self._commit_editor_value(editor, row, col)
            editor.clearFocus()
            self.table.setFocus()
            return self._apply_target(self._move_left(row, col), start_edit=True)

        if key == Qt.Key_Right:
            self._commit_editor_value(editor, row, col)
            editor.clearFocus()
            self.table.setFocus()
            return self._apply_target(self._move_right(row, col), start_edit=True)

        return False

    def eventFilter(self, watched: QObject, event: QEvent):  # noqa: N802
        if event.type() != QEvent.KeyPress:
            return super().eventFilter(watched, event)

        key = int(event.key())
        modifiers = int(event.modifiers())
        nav_keys = {
            Qt.Key_Return,
            Qt.Key_Enter,
            Qt.Key_Tab,
            Qt.Key_Backtab,
            Qt.Key_Up,
            Qt.Key_Down,
            Qt.Key_Left,
            Qt.Key_Right,
        }
        if key not in nav_keys:
            return super().eventFilter(watched, event)

        if watched in (self.table, self.table.viewport()):
            if self._handle_table_key(key, modifiers):
                return True
            return super().eventFilter(watched, event)

        pos = self._editor_positions.get(id(watched))
        if pos is None:
            return super().eventFilter(watched, event)
        row, col = pos
        if self._handle_editor_key(watched, row, col, key, modifiers):
            return True
        return super().eventFilter(watched, event)

