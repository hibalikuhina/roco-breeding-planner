"""把程序打包成 dist/ 下不需要任何依赖的单文件 Windows exe。

每次修改代码或图鉴数据后运行：python build_exe.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAME = "RocoBreedingPlanner"


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller is missing. Install it with:  python -m pip install pyinstaller")
        return 1
    for folder in ("build", "dist"):
        shutil.rmtree(ROOT / folder, ignore_errors=True)
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--onefile", "--windowed", "--name", NAME,
        # 只打包只读图鉴；个人记录始终留在用户数据目录，绝不打包。
        "--add-data", f"{ROOT / 'data'}{';' if sys.platform == 'win32' else ':'}data",
        "--specpath", str(ROOT / "build"),
        "--workpath", str(ROOT / "build"),
        "--distpath", str(ROOT / "dist"),
        str(ROOT / "app.py"),
    ]
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode == 0:
        print(f"\nBuilt {ROOT / 'dist' / (NAME + '.exe')}")
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
