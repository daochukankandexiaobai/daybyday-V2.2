# 字段盘点报告

本文档记录当前版本字段配置驱动改造的第一阶段结果。本阶段只建立字段注册中心和盘点文档，不改变 UI、数据库、保存、查询、导出等现有行为。

## 1. 字段注册中心

当前项目已有字段配置雏形，本阶段复用并增强以下模块：

- `app/config/field_registry.py`：字段注册中心，定义字段元数据、分类、默认值、格式、聚合方式、页面可见性查询接口。
- `app/config/field_groups.py`：字段分组与页面字段集合。
- `app/config/field_profiles.py`：数据录入、今日展示、查询汇总、分析、PNG 等字段展示 profile。
- `app/config/field_rules.py`：字段格式、默认值、聚合方式读取接口。
- `app/config/field_compat.py`：旧页面和模板逻辑的兼容读取接口。
- `app/utils/field_utils.py`、`app/services/field_service.py`：字段中心的工具层和 service facade。

## 2. 字段分类

字段中心支持以下分类：

- `raw_daily`：用户每日录入的原始日报字段。
- `config`：基础配置、目标配置字段。
- `cumulative`：累计字段。
- `formula`：公式字段。
- `display`：页面展示辅助字段。

## 3. 原始日报字段

以下字段属于每日录入原始字段：

- `repayment_amount_daily`：当日回款金额
- `loan_amount_daily`：当日放款金额
- `intention_daily`：当日意向
- `wechat_count_daily`：当日微信量
- `visit_count_daily`：当日上门量
- `invalid_visit_count_daily`：当日无效上门
- `signing_count_daily`：当日签约量
- `quality_visit_count_daily`：当日优质上门
- `approval_customer_count_daily`：当日批复客户数
- `repayment_customer_count_daily`：当日回款客户数
- `debt_case_submit_count_daily`：当日债重进件数
- `debt_case_repayment_count_daily`：当日债重回款件数
- `debt_case_repayment_amount_daily`：当日债重回款金额
- `large_order_repayment_count_daily`：当日大单回款笔数
- `large_order_repayment_amount_daily`：当日大单回款金额
- `four_star_customer_count_daily`：当日四星客户数
- `five_star_customer_count_daily`：当日五星客户数
- `remark`：备注

## 4. 基础展示字段

- `record_date`：日期
- `query_range`：查询区间
- `region`：区域
- `team_id`：团队ID
- `team_name_snapshot`：团队
- `team_name`：团队
- `team_manager_name_snapshot`：团队经理姓名
- `account_manager_id`：客户经理ID
- `account_manager_name_snapshot`：客户经理姓名
- `account_manager_name`：客户经理
- `settlement_cycle_code`：结算周期
- `cycle_target`：结算周期目标
- `team_cycle_target`：结算周期目标

## 5. 累计字段

- `repayment_amount_cumulative`：累计回款金额
- `loan_amount_cumulative`：累计放款金额
- `invitation_cumulative`：累计邀约
- `signing_count_cumulative`：累计签约量
- `quality_visit_count_cumulative`：累计优质上门量

## 6. 公式字段

- `target_progress`：目标完成进度
- `daily_signing_rate`：当日签约率
- `signing_rate`：签约率
- `daily_quality_visit_rate`：当日优质上门率
- `quality_visit_rate`：优质上门率
- `daily_approval_rate`：当日批复率
- `approval_rate`：批复率
- `daily_sales_conversion_rate`：当日销售转化率
- `sales_conversion_rate`：销售转化率
- `repayment_conversion_rate`：回款转化率
- `warrant_conversion_rate`：权证转化率

## 7. 目标字段

- `visit_target`：周上门目标
- `quality_visit_target`：周优质上门目标
- `repayment_target`：周回款目标
- `cycle_repayment_target`：月度/结算周期回款目标

这些字段当前仅作为配置元数据纳入字段中心，不改变 `weekly_targets` 表结构，也不改变现有目标设置窗口与服务层行为。

## 8. 当前仍存在硬编码字段的位置

以下位置仍保留现有硬编码或半硬编码字段定义，本阶段不迁移，避免一次性改动过大：

- `app/ui/tabs/entry_table_config.py`：数据录入表列配置、列宽、紧凑显示名。
- `app/ui/tabs/preview_tab.py`：今日展示表格字段读取字段 profile，但仍保留页面渲染逻辑。
- `app/ui/tabs/query_tab.py`：查询汇总表字段读取字段 profile，但仍保留页面渲染逻辑。
- `app/ui/tabs/analysis_tab.py`：KPI、图表、指标展示仍有页面级配置。
- `app/services/excel_service.py`：汇总 sheet、目标 sheet、预警 sheet 仍有导出列定义。
- `app/services/report_image_service.py`：PNG 分图/总图绘制与摘要逻辑仍有导出布局规则。
- `app/services/export_service.py`：JSON payload 已使用配置字段，但导入兼容逻辑仍保留旧结构。
- `app/ui/tabs/legacy_migration_tab.py`：旧数据迁移预览字段仍为独立固定列。
- `app/ui/tabs/local_data_manage_tab.py`：本地数据管理编辑字段仍为独立固定列。

## 9. 后续建议迁移顺序

1. 数据录入页：保留 `entry_table_config.py`，但逐步从字段中心读取字段名、类型、默认值、校验规则。
2. 今日展示页：将表格字段、格式化、导出字段完全收敛到字段 profile。
3. 查询汇总页：将聚合字段、公式字段、显示字段分组收敛到字段中心。
4. 数据分析页：将可选指标、图表支持类型、默认指标从字段中心读取。
5. Excel/PNG/JSON 导出：将表头、格式、导出字段、预警扩展字段逐步配置化。
6. 旧数据迁移和本地数据管理：最后迁移，避免影响管理端修复能力。

## 10. 本阶段不改动的内容

- 不改 `daily_records` 表。
- 不新增动态指标表。
- 不改 UI 页面生成逻辑。
- 不删除旧字段列表。
- 不改查询汇总聚合口径。
- 不改 JSON、Excel、PNG 导出结构。
- 不改结算周期规则。
