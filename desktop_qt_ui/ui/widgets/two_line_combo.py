"""Combo box that shows a large title and a smaller subtitle even when closed."""

from PyQt6.QtCore import QRect, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPalette
from PyQt6.QtWidgets import (
    QListView,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionComboBox,
    QStyleOptionViewItem,
    QStylePainter,
)

from ui.theme import get_current_theme_colors, malgun_gothic_bold_font
from ui.widgets.wheel_filter import NoWheelComboBox

SUBTITLE_ROLE = Qt.ItemDataRole.UserRole
ITEM_HEIGHT = 72
CLOSED_HEIGHT = 75
TITLE_PX = 21
LIST_TITLE_PX = 18
SUBTITLE_PX = 12
PAD_X = 12
PAD_Y = 8
TITLE_H = 24
TITLE_SUBTITLE_GAP = 6
CLOSED_TITLE_SUBTITLE_GAP = TITLE_SUBTITLE_GAP + 3
CLOSED_PAD_LEFT = 12
CLOSED_PAD_TOP = 4
CLOSED_PAD_RIGHT = 29
CLOSED_TRAILING_TOP = 35
CLOSED_TRAILING_LABEL_PX = 13
CLOSED_TRAILING_ARROW_PX = 15
CLOSED_ARROW = "▾"


def _draw_two_line_text(painter, rect, title, subtitle, *, selected=False, tight=False):
    colors = get_current_theme_colors()
    if selected:
        title_color = painter.pen().color()
        subtitle_color = title_color
    else:
        title_color = QColor(colors.get("text_page_title", "#F8FAFC"))
        subtitle_color = (
            title_color
            if tight
            else QColor(colors.get("text_page_subtitle", "#94A3B8"))
        )

    pad_x = 0 if tight else PAD_X
    pad_y = 0 if tight else PAD_Y
    inner = rect.adjusted(pad_x, pad_y, -pad_x, -pad_y)
    painter.save()
    original_font = QFont(painter.font())

    title_font = malgun_gothic_bold_font(TITLE_PX if tight else LIST_TITLE_PX)
    painter.setFont(title_font)
    painter.setPen(title_color)
    title_h = painter.fontMetrics().height() if tight else TITLE_H
    title_rect = QRect(inner.left(), inner.top(), inner.width(), title_h)
    painter.drawText(
        title_rect,
        int(
            Qt.AlignmentFlag.AlignLeft
            | (Qt.AlignmentFlag.AlignTop if tight else Qt.AlignmentFlag.AlignVCenter)
        ),
        title,
    )

    if subtitle:
        sub_font = QFont(original_font)
        sub_font.setPixelSize(SUBTITLE_PX)
        sub_font.setWeight(QFont.Weight.Normal)
        painter.setFont(sub_font)
        painter.setPen(subtitle_color)
        gap = CLOSED_TITLE_SUBTITLE_GAP if tight else TITLE_SUBTITLE_GAP
        sub_top = title_rect.bottom() + gap
        sub_rect = QRect(
            inner.left(),
            sub_top,
            inner.width(),
            max(0, inner.bottom() - sub_top),
        )
        painter.drawText(
            sub_rect,
            int(
                Qt.AlignmentFlag.AlignLeft
                | Qt.AlignmentFlag.AlignTop
                | Qt.TextFlag.TextWordWrap
            ),
            subtitle.replace("\n", " "),
        )
    painter.restore()


class TwoLineItemDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        widget = option.widget
        style = widget.style() if widget is not None else None
        if style is not None:
            style.drawPrimitive(
                QStyle.PrimitiveElement.PE_PanelItemViewItem, opt, painter, widget
            )
        elif opt.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(opt.rect, opt.palette.highlight())

        title = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        subtitle = str(index.data(SUBTITLE_ROLE) or "")
        selected = bool(opt.state & QStyle.StateFlag.State_Selected)
        if selected:
            painter.setPen(opt.palette.color(QPalette.ColorRole.HighlightedText))
        _draw_two_line_text(painter, opt.rect, title, subtitle, selected=selected)

    def sizeHint(self, option, index):
        return QSize(max(option.rect.width(), 200), ITEM_HEIGHT)


class TwoLineComboBox(NoWheelComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        view = QListView(self)
        view.setTextElideMode(Qt.TextElideMode.ElideNone)
        view.setUniformItemSizes(True)
        view.setItemDelegate(TwoLineItemDelegate(view))
        view.setCursor(Qt.CursorShape.ArrowCursor)
        view.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        self.setView(view)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setItemDelegate(TwoLineItemDelegate(self))
        self.setMaxVisibleItems(8)
        self.setFixedHeight(CLOSED_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._closed_trailing_text = ""

    def setClosedTrailingText(self, text: str):
        self._closed_trailing_text = text or ""
        self.update()

    def sizeHint(self):
        hint = super().sizeHint()
        hint.setHeight(CLOSED_HEIGHT)
        return hint

    def minimumSizeHint(self):
        hint = super().minimumSizeHint()
        hint.setHeight(CLOSED_HEIGHT)
        return hint

    def paintEvent(self, event):
        painter = QStylePainter(self)
        opt = QStyleOptionComboBox()
        self.initStyleOption(opt)
        opt.currentText = ""
        opt.frame = False
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, opt)

        text_rect = self.contentsRect().adjusted(
            CLOSED_PAD_LEFT, CLOSED_PAD_TOP, -CLOSED_PAD_RIGHT, 0
        )
        index = self.currentIndex()
        title = self.itemText(index) if index >= 0 else ""
        subtitle = str(self.itemData(index, SUBTITLE_ROLE) or "") if index >= 0 else ""
        _draw_two_line_text(painter, text_rect, title, subtitle, selected=False, tight=True)
        self._draw_closed_trailing_text(painter, text_rect)

    def _draw_closed_trailing_text(self, painter, rect):
        trailing = (self._closed_trailing_text or "").replace(CLOSED_ARROW, "").strip()
        if not trailing and not CLOSED_ARROW:
            return
        colors = get_current_theme_colors()
        painter.setPen(QColor(colors.get("text_page_subtitle", "#94A3B8")))

        label_font = QFont(painter.font())
        label_font.setPixelSize(CLOSED_TRAILING_LABEL_PX)
        label_font.setWeight(QFont.Weight.DemiBold)
        arrow_font = QFont(painter.font())
        arrow_font.setPixelSize(CLOSED_TRAILING_ARROW_PX)
        arrow_font.setWeight(QFont.Weight.DemiBold)

        label_fm = QFontMetrics(label_font)
        arrow_fm = QFontMetrics(arrow_font)
        arrow_w = arrow_fm.horizontalAdvance(CLOSED_ARROW)
        gap = label_fm.horizontalAdvance(" ") if trailing else 0
        arrow_x = rect.right() - arrow_w
        label_x = arrow_x - gap - label_fm.horizontalAdvance(trailing)
        top = self.contentsRect().top() + CLOSED_TRAILING_TOP

        painter.setFont(arrow_font)
        painter.drawText(arrow_x, top + arrow_fm.ascent(), CLOSED_ARROW)
        if trailing:
            painter.setFont(label_font)
            painter.drawText(label_x, top + label_fm.ascent(), trailing)

    def _apply_popup_menu_border(self):
        colors = get_current_theme_colors()
        border = colors.get("border_card", "rgba(255, 255, 255, 0.08)")
        bg = colors.get("bg_surface_raised", colors.get("bg_dropdown", "#0E1428"))
        selection = colors.get("dropdown_selection", border)
        selection_text = colors.get("list_item_selected_text", colors.get("text_bright", "#FFFFFF"))
        frame_css = f"""
            background: {bg};
            background-color: {bg};
            border: 1px solid {border};
            border-radius: 0px;
        """
        view = self.view()
        if view is not None:
            view.setStyleSheet(
                f"""
                QAbstractItemView {{
                    {frame_css}
                    outline: none;
                    selection-background-color: {selection};
                    selection-color: {selection_text};
                }}
                """
            )
        container = view.parentWidget() if view is not None else None
        if container is not None:
            container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            container.setStyleSheet(f"QFrame {{ {frame_css} }}")

    def showPopup(self):
        controller = getattr(self, "_hover_hint_controller", None)
        if controller is not None:
            hide = getattr(controller, "_hide_hint", None)
            if callable(hide):
                hide()
        view = self.view()
        visible = max(1, min(self.count(), self.maxVisibleItems()))
        popup_h = visible * ITEM_HEIGHT + 4
        view.setMinimumWidth(max(self.width(), 420))
        view.setMinimumHeight(popup_h)
        super().showPopup()
        container = view.parentWidget()
        if container is not None:
            container.setMinimumHeight(popup_h)
        self._apply_popup_menu_border()
        self._set_open_cursors()

    def hidePopup(self):
        super().hidePopup()
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _set_open_cursors(self):
        self.setCursor(Qt.CursorShape.ArrowCursor)
        view = self.view()
        if view is None:
            return
        view.setCursor(Qt.CursorShape.ArrowCursor)
        viewport = view.viewport()
        if viewport is not None:
            viewport.setCursor(Qt.CursorShape.ArrowCursor)
        container = view.parentWidget()
        if container is not None:
            container.setCursor(Qt.CursorShape.ArrowCursor)
