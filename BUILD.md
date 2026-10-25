# 打包与更新

`dist/RocoBreedingPlanner.exe` 是用 PyInstaller 打成的单文件程序，内含 Python 运行时、tkinter 和 `data/pokedex.json`。exe 不会随源码自动更新，**每次修改代码或图鉴数据后都要重新打包**，否则分享出去的仍是旧版。

## 什么时候要重新打包

改动以下任一文件之后：

- `app.py`、`engine.py`（程序逻辑和界面）
- `data/pokedex.json`（包括运行 `refresh_pokedex.py` 刷新图鉴之后）
- `build_exe.py`（打包参数）

只改 README、测试或 `launch.cmd` 时不需要重新打包。

## 打包步骤

1. 第一次打包前安装 PyInstaller（只有打包的人需要，使用者不需要）：

   ```powershell
   python -m pip install pyinstaller
   ```

2. 先跑测试：

   ```powershell
   python -m unittest test_routes
   ```

3. 打包：

   ```powershell
   python build_exe.py
   ```

   脚本会先清空 `build/` 和 `dist/`，再生成 `dist/RocoBreedingPlanner.exe`。这两个文件夹都不进 Git。

4. 双击新 exe 检查：窗口能打开、没有命令行窗口、原有账号和记录都在。
5. 把新 exe 发给使用者，让他们直接替换旧 exe。

## 用户数据注意事项

exe 里只打包只读的图鉴，**个人数据从不打包进 exe**，而是放在 `%APPDATA%\RocoBreedingPlanner\personal.sqlite3`（便携模式下放在 exe 旁的 `user_data\`）。所以使用者替换新版 exe 时数据会保留。更新时要守住这一点：

- **数据库结构只能做向后兼容的修改。** 新增表或列时，照 `app.py` 中 `db()` 的写法，先检查列是否存在再 `ALTER TABLE ... ADD COLUMN`，让旧数据库打开时自动升级。不要删除或重命名已有的表和列，也不要改变已有字段的含义，否则使用者的旧数据会读不出来或被误读。
- 不要改动 `APP_DIR_NAME`、数据库文件名和便携模式文件夹名 `user_data`。改动后新版 exe 会找不到旧数据，就像全新安装一样。
- 不要把 `user_data/` 或任何 `.sqlite3` 文件加进 `--add-data`。
- 设置项写在 `settings` 表里。新增设置项时，要为旧数据库里缺这一项的情况准备默认值。
- 改动数据结构前，先备份自己的 `personal.sqlite3`，再用这份旧数据测试新版 exe。
- 「导入数据」会整体替换数据库。导入旧版本导出的文件后，`db()` 会照常自动补齐新列，所以上面的向后兼容规则同样保证导入能用。
- 从 Claude 桌面版等 MSIX 打包应用里启动程序时，`%APPDATA%` 的写入会被系统重定向到 `%LOCALAPPDATA%\Packages\<应用>\LocalCache\Roaming`，看到的并不是你平时双击 exe 用的那份数据。验证数据时，请从资源管理器双击启动。
