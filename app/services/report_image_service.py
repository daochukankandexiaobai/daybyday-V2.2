from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from app.config.field_profiles import PNG_SECTION_PROFILES, PROFILE_PREVIEW_TABLE, get_profile_field_keys
from app.utils.qt_compat import QRect, Qt
from app.utils.qt_compat import QColor, QFont, QFontMetrics, QImage, QPainter, QPen

from app.utils.file_utils import ensure_dir, sanitize_component
from app.utils.log_utils import get_logger


@dataclass(frozen=True)
class ImageSectionSpec:
    index: int
    title: str
    file_suffix: str
    column_indexes: tuple[int, ...]


_PREVIEW_FIELD_KEYS = get_profile_field_keys(PROFILE_PREVIEW_TABLE)
_PREVIEW_FIELD_INDEXES = {field_key: idx for idx, field_key in enumerate(_PREVIEW_FIELD_KEYS)}


def _build_image_section_specs() -> tuple[ImageSectionSpec, ...]:
    specs: list[ImageSectionSpec] = []
    for profile in PNG_SECTION_PROFILES:
        column_indexes = tuple(
            _PREVIEW_FIELD_INDEXES[field_key]
            for field_key in profile.field_keys
            if field_key in _PREVIEW_FIELD_INDEXES
        )
        specs.append(
            ImageSectionSpec(
                index=profile.index,
                title=profile.title,
                file_suffix=profile.file_suffix,
                column_indexes=column_indexes,
            )
        )
    return tuple(specs)


class ReportImageService:
    """今日展示图片导出服务：4张分图 + 1张纵向总图。"""

    SECTION_SPECS: tuple[ImageSectionSpec, ...] = _build_image_section_specs()

    def __init__(self) -> None:
        self.logger = get_logger("report_image_service")
        self.logo_image = self._load_logo()

    @staticmethod
    def _logo_path() -> Path:
        return Path(__file__).resolve().parents[2] / "assets" / "银税logo.png"

    def _load_logo(self) -> QImage | None:
        logo_path = self._logo_path()
        if not logo_path.exists():
            self.logger.warning("Logo 文件不存在: %s", logo_path)
            return None

        image = QImage(str(logo_path))
        if image.isNull():
            self.logger.warning("Logo 文件读取失败: %s", logo_path)
            return None
        return image

    def _scaled_logo(self, size: int) -> QImage | None:
        if self.logo_image is None:
            return None
        return self.logo_image.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def export_today_preview_bundle(
        self,
        *,
        output_dir: str | Path,
        record_date: str,
        settlement_cycle_code: str,
        region: str,
        team_name: str,
        team_manager_name: str,
        headers: Sequence[str],
        rows: Sequence[Sequence[str]],
    ) -> dict[str, str | list[str]]:
        """导出分图和总图，返回全部输出路径。"""
        out_dir = ensure_dir(str(output_dir))
        prefix = self._build_prefix(record_date, settlement_cycle_code)
        info_line = self._build_info_line(record_date, settlement_cycle_code, region, team_name, team_manager_name)

        part_paths: list[str] = []
        part_images: list[QImage] = []
        for spec in self.SECTION_SPECS:
            section_headers, section_rows = self._slice_rows(headers, rows, spec.column_indexes)
            image = self._render_table_image(
                title=spec.title,
                info_line=info_line,
                headers=section_headers,
                rows=section_rows,
            )
            file_name = f"{prefix}_{spec.index:02d}_{spec.file_suffix}.png"
            file_path = out_dir / file_name
            if not image.save(str(file_path), "PNG"):
                raise RuntimeError(f"分图保存失败: {file_path}")
            part_paths.append(str(file_path))
            part_images.append(image)

        total_image = self._compose_total_image(
            title="今日展示汇总图",
            info_line=info_line,
            part_images=part_images,
        )
        total_path = out_dir / f"{prefix}_总图.png"
        if not total_image.save(str(total_path), "PNG"):
            raise RuntimeError(f"总图保存失败: {total_path}")

        self.logger.info(
            "今日展示图片导出成功 dir=%s total=%s parts=%s",
            out_dir,
            total_path,
            ",".join(part_paths),
        )
        return {
            "output_dir": str(out_dir),
            "total_path": str(total_path),
            "part_paths": part_paths,
        }

    @staticmethod
    def _slice_rows(
        headers: Sequence[str],
        rows: Sequence[Sequence[str]],
        column_indexes: tuple[int, ...],
    ) -> tuple[list[str], list[list[str]]]:
        section_headers = [str(headers[idx]) if idx < len(headers) else "" for idx in column_indexes]
        section_rows: list[list[str]] = []
        for row in rows:
            section_rows.append([str(row[idx]) if idx < len(row) else "" for idx in column_indexes])
        return section_headers, section_rows

    @staticmethod
    def _build_prefix(record_date: str, settlement_cycle_code: str) -> str:
        safe_cycle = sanitize_component(settlement_cycle_code or "未知周期")
        safe_date = sanitize_component(record_date or "未知日期")
        return f"今日展示_{safe_cycle}_{safe_date}"

    @staticmethod
    def _build_info_line(
        record_date: str,
        settlement_cycle_code: str,
        region: str,
        team_name: str,
        team_manager_name: str,
    ) -> str:
        date_part = f"日期：{record_date or '-'}"
        cycle_part = f"结算周期：{settlement_cycle_code or '-'}"
        team_part = f"团队：{team_name or '-'}"
        manager_part = f"团队经理：{team_manager_name or '-'}"
        region_part = f"区域：{region or '-'}"
        return "  |  ".join([date_part, cycle_part, region_part, team_part, manager_part])

    @staticmethod
    def _is_numeric_text(text: str) -> bool:
        return bool(re.fullmatch(r"-?\d+(\.\d+)?%?", text.strip()))

    @staticmethod
    def _is_summary_row(row: Sequence[str]) -> bool:
        if not row:
            return False
        first = str(row[0]).strip()
        return first in {"团队汇总", "汇总"}

    def _calc_column_widths(
        self,
        headers: Sequence[str],
        rows: Sequence[Sequence[str]],
        header_font: QFont,
        body_font: QFont,
    ) -> list[int]:
        header_fm = QFontMetrics(header_font)
        body_fm = QFontMetrics(body_font)

        widths: list[int] = []
        for col, header in enumerate(headers):
            max_width = header_fm.horizontalAdvance(header)
            for row in rows:
                text = row[col] if col < len(row) else ""
                max_width = max(max_width, body_fm.horizontalAdvance(str(text)))

            min_width = 90
            if header in {"日期", "客户经理"}:
                min_width = 120
            elif "金额" in header or "目标" in header:
                min_width = 130
            elif "率" in header:
                min_width = 120

            widths.append(max(min_width, min(360, max_width + 24)))
        return widths

    def _render_table_image(
        self,
        *,
        title: str,
        info_line: str,
        headers: Sequence[str],
        rows: Sequence[Sequence[str]],
    ) -> QImage:
        margin = 20
        title_h = 38
        info_h = 26
        header_h = 36
        row_h = 32

        title_font = QFont("Microsoft YaHei", 14)
        title_font.setBold(True)

        info_font = QFont("Microsoft YaHei", 10)
        header_font = QFont("Microsoft YaHei", 10)
        header_font.setBold(True)
        body_font = QFont("Microsoft YaHei", 10)

        widths = self._calc_column_widths(headers, rows, header_font, body_font)
        table_width = sum(widths)
        table_height = header_h + len(rows) * row_h

        image_width = margin * 2 + table_width
        image_height = margin * 2 + title_h + info_h + table_height

        image = QImage(image_width, image_height, QImage.Format_ARGB32)
        image.fill(QColor("#FFFFFF"))

        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing, False)

        # 标题 + logo
        logo = self._scaled_logo(30)
        title_x = margin
        if logo is not None:
            logo_y = margin + max(0, (title_h - logo.height()) // 2)
            painter.drawImage(title_x, logo_y, logo)
            title_x += logo.width() + 10

        painter.setPen(QColor("#1F2937"))
        painter.setFont(title_font)
        painter.drawText(QRect(title_x, margin, table_width - (title_x - margin), title_h), Qt.AlignLeft | Qt.AlignVCenter, title)

        # 基础信息
        painter.setPen(QColor("#4B5563"))
        painter.setFont(info_font)
        painter.drawText(QRect(title_x, margin + title_h, table_width - (title_x - margin), info_h), Qt.AlignLeft | Qt.AlignVCenter, info_line)

        table_top = margin + title_h + info_h

        header_bg = QColor("#EFF6FF")
        grid_color = QColor("#CBD5E1")
        alt_bg = QColor("#F8FAFC")

        # 绘制表头
        x = margin
        painter.setFont(header_font)
        for col, header in enumerate(headers):
            w = widths[col]
            rect = QRect(x, table_top, w, header_h)
            painter.fillRect(rect, header_bg)
            painter.setPen(QPen(grid_color, 1))
            painter.drawRect(rect)
            painter.setPen(QColor("#111827"))
            painter.drawText(rect.adjusted(8, 0, -8, 0), Qt.AlignVCenter | Qt.AlignLeft, str(header))
            x += w

        # 绘制数据行
        painter.setFont(body_font)
        for row_idx, row in enumerate(rows):
            row_top = table_top + header_h + row_idx * row_h
            x = margin
            is_summary_row = self._is_summary_row(row)
            if is_summary_row:
                painter.fillRect(QRect(margin, row_top, table_width, row_h), QColor("#0B3D91"))
            elif row_idx % 2 == 1:
                painter.fillRect(QRect(margin, row_top, table_width, row_h), alt_bg)

            row_font = QFont(body_font)
            if is_summary_row:
                row_font.setBold(True)
            painter.setFont(row_font)
            for col, text in enumerate(row):
                w = widths[col]
                rect = QRect(x, row_top, w, row_h)
                if is_summary_row:
                    painter.setPen(QPen(QColor("#07285E"), 2))
                else:
                    painter.setPen(QPen(grid_color, 1))
                painter.drawRect(rect)
                painter.setPen(QColor("#FFFFFF") if is_summary_row else QColor("#111827"))
                if self._is_numeric_text(str(text)):
                    align = Qt.AlignVCenter | Qt.AlignRight
                    text_rect = rect.adjusted(8, 0, -8, 0)
                else:
                    align = Qt.AlignVCenter | Qt.AlignLeft
                    text_rect = rect.adjusted(8, 0, -8, 0)
                painter.drawText(text_rect, align, str(text))
                x += w

        painter.end()
        return image

    def _compose_total_image(self, *, title: str, info_line: str, part_images: Sequence[QImage]) -> QImage:
        if not part_images:
            raise ValueError("没有可拼接的分图")

        margin = 20
        gap = 18
        title_h = 42
        info_h = 28

        title_font = QFont("Microsoft YaHei", 16)
        title_font.setBold(True)
        info_font = QFont("Microsoft YaHei", 10)

        logo = self._scaled_logo(34)
        logo_offset = (logo.width() + 10) if logo is not None else 0

        title_fm = QFontMetrics(title_font)
        info_fm = QFontMetrics(info_font)

        max_width = max(image.width() for image in part_images)
        max_width = max(
            max_width,
            title_fm.horizontalAdvance(title) + logo_offset + 20,
            info_fm.horizontalAdvance(info_line) + logo_offset + 20,
        )

        content_height = sum(image.height() for image in part_images) + gap * (len(part_images) - 1)
        canvas_width = max_width + margin * 2
        canvas_height = margin * 2 + title_h + info_h + content_height

        canvas = QImage(canvas_width, canvas_height, QImage.Format_ARGB32)
        canvas.fill(QColor("#FFFFFF"))

        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.Antialiasing, True)

        title_x = margin
        if logo is not None:
            logo_y = margin + max(0, (title_h - logo.height()) // 2)
            painter.drawImage(title_x, logo_y, logo)
            title_x += logo.width() + 10

        painter.setPen(QColor("#111827"))
        painter.setFont(title_font)
        painter.drawText(QRect(title_x, margin, max_width - (title_x - margin), title_h), Qt.AlignLeft | Qt.AlignVCenter, title)

        painter.setPen(QColor("#4B5563"))
        painter.setFont(info_font)
        painter.drawText(QRect(title_x, margin + title_h, max_width - (title_x - margin), info_h), Qt.AlignLeft | Qt.AlignVCenter, info_line)

        y = margin + title_h + info_h
        for idx, image in enumerate(part_images):
            x = margin + (max_width - image.width()) // 2
            painter.drawImage(x, y, image)
            y += image.height()
            if idx < len(part_images) - 1:
                painter.setPen(QPen(QColor("#D1D5DB"), 1))
                painter.drawLine(margin, y + gap // 2, margin + max_width, y + gap // 2)
                y += gap

        painter.end()
        return canvas
