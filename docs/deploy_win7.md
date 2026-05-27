# Win7 部署指南（x64）

## 1. 推荐构建环境
- 操作系统：Windows 10/11 x64（用于打包）
- Python：3.8.x（必须）
- 依赖：`requirements-dev.txt`

> 说明：Win7 目标机不能使用 Python 3.11 + PySide6。本兼容分支改为 Python 3.8 + PySide2。

## 2. 推荐运行环境（目标机）
- Windows 7 SP1 x64
- 安装 VC++ 运行库（若缺失，程序启动会失败）
- 建议将程序放在可写目录，例如：`D:\TeamReportApp`，避免 `Program Files` 权限限制。

## 3. 安装与打包

### 3.1 安装依赖
```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements-dev.txt
```

### 3.2 打包（目录版，推荐）
```powershell
pyinstaller --noconfirm --clean --windowed --onedir --name TeamReportAppWin7 --add-data "assets;assets" main.py
```

输出目录：`dist\TeamReportAppWin7\`

## 4. 首次启动说明
1. 双击 `TeamReportAppWin7.exe`
2. 程序会自动初始化数据库（`data\team_report.db`）
3. 默认管理员账号：
   - 用户名：`admin`
   - 密码：`admin123`
4. 首次登录后请在“系统设置”修改管理员密码。

## 5. 常见问题排查

### 5.1 启动即闪退
- 检查 VC++ 运行库是否安装
- 在命令行启动查看日志：
  ```powershell
  TeamReportAppWin7.exe
  ```
- 查看日志文件：`logs\app.log`、`logs\error_YYYYMMDD.log`

### 5.2 无法写入导出文件
- 检查目录权限（JSON/Excel/PNG 导出）
- 建议导出到 `D:\exports` 等可写目录

### 5.3 中文路径问题
- 本项目已使用 UTF-8 + pathlib 路径处理
- 若目标机系统区域设置异常，建议将程序目录与导出目录放在英文路径进行对比测试

## 6. 验证脚本

### 6.1 运行时兼容检查
```powershell
python scripts\check_win7_compat.py
```

### 6.2 冒烟测试（业务闭环）
```powershell
python scripts\smoke_test_win7.py
```

覆盖项：主窗口/Tab 初始化、管理员登录、SQLite 初始化、日报保存、查询聚合、JSON 导入导出、Excel 导出、PNG 分图与总图导出。
