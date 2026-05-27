# Win7 兼容迁移说明（v1.1-win7）

## 本次迁移目标
在不改变业务口径与数据结构的前提下，将运行时从：
- Python 3.11 + PySide6
迁移到：
- Python 3.8 + PySide2（Win7 可用）

## 主要改动

1. Qt 兼容层
- 新增 `app/utils/qt_compat.py`
- 所有 UI 与 Qt 相关模块统一改为从兼容层导入
- 统一 `app_exec/dialog_exec`，兼容 `exec/exec_` 差异

2. 依赖调整
- 新增 `requirements-win7.txt`（Python 3.8 + PySide2）
- 新增 `requirements-dev.txt`（含 PyInstaller）
- `requirements.txt` 指向 Win7 运行依赖

3. Python 3.8 兼容修正
- 移除 `@dataclass(slots=True)`（3.10+ 特性）
- 保留现有业务逻辑与口径不变

4. 启动前检查
- 新增 `app/utils/runtime_check.py`
- 启动时检查 Python 版本、目录可写性并记录日志

5. 验证脚本
- 新增 `scripts/check_win7_compat.py`
- 新增 `scripts/smoke_test_win7.py`

## 改动较大模块
- `app/ui/*`（Qt 导入迁移）
- `main.py`（兼容启动与运行检查）
- `app/services/report_image_service.py`（Qt 导入迁移）

## 回切到 Win10/11 + PySide6 的建议
1. 保留 `qt_compat.py`，只调整其导入优先级即可
2. 新增 `requirements-win11.txt`，将 PySide6 作为该分支主依赖
3. 不要改业务服务层，避免引入口径分叉
4. 通过 CI 分别验证 `win7-compat` 与 `mainline-pyside6` 两套依赖
