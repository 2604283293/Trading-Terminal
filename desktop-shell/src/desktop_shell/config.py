"""统一配置 — 版本号、数据路径、GitHub 仓库信息。"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _read_version() -> str:
    """读取 VERSION 文件。开发环境从项目根目录读，打包环境从 PyInstaller 资源目录读。"""
    if getattr(sys, "frozen", False):
        # PyInstaller 打包后
        version_file = Path(sys._MEIPASS) / "VERSION"
    else:
        # 开发环境: desktop-shell/src/desktop_shell/config.py → parents[3] = 项目根目录
        version_file = Path(__file__).resolve().parents[3] / "VERSION"
    if version_file.exists():
        return version_file.read_text(encoding="utf-8").strip()
    return "0.0.0"


def get_data_root() -> Path:
    """数据目录：打包后用 %LOCALAPPDATA%，开发环境用项目 data/。"""
    if getattr(sys, "frozen", False):
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "Trading-Terminal" / "data"
    return Path(__file__).resolve().parents[3] / "data"


def get_config_dir() -> Path:
    """配置目录：打包后用 %LOCALAPPDATA%，开发环境用项目根目录。"""
    if getattr(sys, "frozen", False):
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "Trading-Terminal"
    return Path(__file__).resolve().parents[3]


def ensure_data_dirs() -> None:
    """确保 data 子目录全部存在。"""
    root = get_data_root()
    subdirs = [
        "actions", "stocks", "billboard", "northbound", "sector_flow",
        "daily_dump", "hot_rank", "dragon_tiger", "dragon_tiger_seats",
    ]
    for sub in subdirs:
        (root / sub).mkdir(parents=True, exist_ok=True)


APP_VERSION = _read_version()
GITHUB_REPO = "2604283293/Trading-Terminal"
GITHUB_API = f"https://api.github.com/repos/{GITHUB_REPO}"

# 反馈提交的 GitHub token（打包时注入到 config.json，开发时读环境变量）
_GITHUB_TOKEN = os.environ.get("FEEDBACK_GITHUB_TOKEN", "")


def get_github_token() -> str:
    """获取 GitHub token（用于提交 feedback issues）。"""
    # 优先从环境变量
    env_token = os.environ.get("FEEDBACK_GITHUB_TOKEN", "")
    if env_token:
        return env_token
    # 打包后从 config.json 读
    config_json = get_config_dir() / "config.json"
    if config_json.exists():
        try:
            import json
            cfg = json.loads(config_json.read_text(encoding="utf-8"))
            return cfg.get("github_token", "")
        except Exception:
            pass
    return _GITHUB_TOKEN
