# 字段配置驱动架构开发说明

## 核心表

- `field_definitions`：字段定义、类型、默认值、统计方式、存储方式
- `field_page_visibility`：字段在数据录入、今日展示、查询汇总、分析、导出中的显示状态和顺序
- `view_templates`：页面模板和 PNG 分图模板
- `daily_metric_values`：动态日报指标值

## 核心服务

- `FieldValueService`：统一读取和写入固定列字段与动态字段
- `DisplayFieldConfigService`：读取页面字段配置，并在配置缺失或损坏时回退默认字段
- `AnalysisConfigService`：读取可分析指标
- `FieldAdminConfigService`：管理员字段配置、备份、导入、恢复默认
- `AggregationService`：统一聚合
- `FormulaService`：统一公式计算

## fixed_column 与 dynamic_metric

`fixed_column` 用于历史稳定字段，值存储在 `daily_records` 固定列中。

`dynamic_metric` 用于后续新增日报字段，值存储在 `daily_metric_values`：

- 不需要给 `daily_records` 新增列
- 通过 `record_id + field_key` 唯一定位
- 停用字段不删除历史值

页面和导出层应通过 `FieldValueService` 读取字段值，不直接判断底层存储。

## 新增字段推荐流程

1. 管理员页面新增字段。
2. 字段分类选择 `raw_daily`。
3. 存储方式由服务自动设为 `dynamic_metric`。
4. 勾选需要显示的页面和导出位置。
5. 保存配置。
6. 运行 `scripts/full_regression_check.py` 和 `scripts/smoke_test.py`。

## 公式字段原则

公式字段不能直接求和或求平均。

例如签约率必须使用：

```text
总签约量 / (总上门量 - 总无效上门量)
```

不能使用每日签约率的平均值。

公式只能使用 `FormulaService` 内置公式，不允许管理员输入 Python 表达式。

## 异常回退策略

- 字段配置缺失：回退代码默认字段 profile
- 页面模板损坏：回退代码默认模板
- PNG 模板字段不存在：跳过字段并记录日志
- 公式字段缺少 `formula_id`：返回空值
- 分母为 0：返回空值，不抛异常

## 旧数据兼容策略

以下兼容层不可随意删除：

- `daily_records` 固定列
- JSON 旧格式导入
- 字段别名和旧模板字段映射
- 旧导入迁移逻辑

清理旧硬编码时，必须先确认页面、导出、导入和测试脚本都不再引用。
