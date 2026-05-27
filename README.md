# 团队经理日报系统 v1.1-win7（Win7 兼容分支）

本分支目标：在 **不改变既有业务逻辑与报表口径** 的前提下，使项目可在 **Windows 7 x64** 环境运行。

## 1. 兼容分支技术栈
- Python 3.8.x
- PySide2（Qt 5.15）
- SQLite
- JSON
- openpyxl

## 2. 为什么不能继续使用 Python 3.11 + PySide6
- Python 3.11 不支持 Windows 7。
- PySide6/Qt6 不支持 Windows 7。
- 因此 Win7 目标机必须使用 Python 3.8 + PySide2 路线。

## 3. 业务逻辑保持不变
以下能力与口径保持不变：
1. 团队经理 -> 多个客户经理模型
2. 结算周期：本月29日~次月28日（显示按结束月命名，如 2026-04期）
3. 周报：周一到周日且被结算周期截断
4. 今日展示、查询汇总字段口径
5. 查询汇总按客户经理聚合（一人一行）
6. JSON 导入导出逻辑
7. Excel 汇总导出逻辑
8. PNG 分图+总图导出逻辑

## 4. 项目内新增兼容模块
- `app/utils/qt_compat.py`
  - 统一 PySide2/PySide6 导入
  - 统一 `app_exec()` / `dialog_exec()`
- `app/utils/runtime_check.py`
  - 启动时环境检查（Python 版本、目录可写性）

## 5. Win7 开发环境搭建
```powershell
cd "E:\工作\day by day"
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements-dev.txt
```

## 6. 运行方式
```powershell
python main.py
```

## 7. 依赖文件说明
- `requirements-win7.txt`：Win7 运行依赖
- `requirements-dev.txt`：开发/打包依赖（包含 PyInstaller）
- `requirements.txt`：默认引用 Win7 依赖

## 8. 默认管理员账号
- 用户名：`admin`
- 密码：`admin123`

首次登录后请在“系统设置”立即修改密码。

## 9. 数据库存放位置
- 默认数据库：`data/team_report.db`
- 首次启动会自动初始化建表与迁移

## 10. JSON / Excel / PNG 导出说明
- JSON：按单团队+单时间范围导出
- Excel：按既有汇总口径导出多 Sheet
- PNG：今日展示页支持 4 张分图 + 1 张总图离屏导出

## 11. Win7 打包
推荐目录版（onedir）：
```powershell
pyinstaller --noconfirm --clean --windowed --onedir --name TeamReportAppWin7 --add-data "assets;assets" main.py
```

输出：`dist\TeamReportAppWin7\`

## 12. Win7 部署文档
详见：
- `docs/deploy_win7.md`
- `docs/win7_migration_notes.md`

## 13. 兼容性验证脚本
### 13.1 运行环境检查
```powershell
python scripts\check_win7_compat.py
```

### 13.2 全链路冒烟测试
```powershell
python scripts\smoke_test_win7.py
```

覆盖：
- 主窗口/Tab 初始化
- 管理员登录
- SQLite 初始化
- 日报保存
- 查询聚合
- JSON 导入导出
- Excel 导出
- PNG 分图+总图导出

## 14. 已知限制
1. 强烈建议在 Win7 x64 + SP1 环境运行。
2. 若目标机缺少 VC++ 运行库，程序可能无法启动。
3. 如果系统字体缺失，PNG 标题显示可能存在差异（已做中文字体优先策略）。
