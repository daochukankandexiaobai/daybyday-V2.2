from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ViewMetrics:
    page_margin: int
    page_spacing: int
    section_margin: int
    section_spacing: int
    control_height: int
    button_height: int
    table_row_height: int
    table_header_height: int
    team_list_max_height: int
    brand_padding_h: int
    brand_padding_v: int
    brand_logo_size: int
    brand_title_font: int
    brand_subtitle_font: int
    nav_tab_padding_h: int
    nav_tab_padding_v: int
    nav_tab_font: int
    entry_top_height: int
    query_filter_height: int
    query_summary_height: int
    kpi_card_height: int
    kpi_columns: int
    analysis_top_height: int
    chart_min_height: int
    chart_toolbar_height: int

