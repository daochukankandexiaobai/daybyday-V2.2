from __future__ import annotations

from dataclasses import dataclass

from app.ui.view_metrics import ViewMetrics


MODE_WIDE = "wide"
MODE_STANDARD = "standard"
MODE_COMPACT = "compact"


@dataclass(frozen=True)
class LayoutProfile:
    mode: str
    min_width: int
    metrics: ViewMetrics


WIDE_PROFILE = LayoutProfile(
    mode=MODE_WIDE,
    min_width=1600,
    metrics=ViewMetrics(
        page_margin=10,
        page_spacing=8,
        section_margin=10,
        section_spacing=8,
        control_height=32,
        button_height=34,
        table_row_height=30,
        table_header_height=34,
        team_list_max_height=120,
        brand_padding_h=10,
        brand_padding_v=4,
        brand_logo_size=28,
        brand_title_font=15,
        brand_subtitle_font=10,
        nav_tab_padding_h=20,
        nav_tab_padding_v=7,
        nav_tab_font=14,
        entry_top_height=188,
        query_filter_height=174,
        query_summary_height=142,
        kpi_card_height=62,
        kpi_columns=5,
        analysis_top_height=300,
        chart_min_height=420,
        chart_toolbar_height=38,
    ),
)

STANDARD_PROFILE = LayoutProfile(
    mode=MODE_STANDARD,
    min_width=1366,
    metrics=ViewMetrics(
        page_margin=8,
        page_spacing=6,
        section_margin=8,
        section_spacing=6,
        control_height=30,
        button_height=32,
        table_row_height=28,
        table_header_height=32,
        team_list_max_height=96,
        brand_padding_h=8,
        brand_padding_v=3,
        brand_logo_size=26,
        brand_title_font=14,
        brand_subtitle_font=9,
        nav_tab_padding_h=16,
        nav_tab_padding_v=6,
        nav_tab_font=13,
        entry_top_height=164,
        query_filter_height=152,
        query_summary_height=124,
        kpi_card_height=54,
        kpi_columns=4,
        analysis_top_height=220,
        chart_min_height=360,
        chart_toolbar_height=34,
    ),
)

COMPACT_PROFILE = LayoutProfile(
    mode=MODE_COMPACT,
    min_width=0,
    metrics=ViewMetrics(
        page_margin=6,
        page_spacing=5,
        section_margin=6,
        section_spacing=5,
        control_height=28,
        button_height=30,
        table_row_height=26,
        table_header_height=30,
        team_list_max_height=82,
        brand_padding_h=6,
        brand_padding_v=2,
        brand_logo_size=24,
        brand_title_font=13,
        brand_subtitle_font=9,
        nav_tab_padding_h=12,
        nav_tab_padding_v=5,
        nav_tab_font=12,
        entry_top_height=150,
        query_filter_height=140,
        query_summary_height=112,
        kpi_card_height=48,
        kpi_columns=4,
        analysis_top_height=180,
        chart_min_height=320,
        chart_toolbar_height=30,
    ),
)


def resolve_layout_profile(window_width: int | None) -> LayoutProfile:
    width = int(window_width or 0)
    if width >= WIDE_PROFILE.min_width:
        return WIDE_PROFILE
    if width >= STANDARD_PROFILE.min_width:
        return STANDARD_PROFILE
    return COMPACT_PROFILE
