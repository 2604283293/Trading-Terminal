"""自动更新 — 后台静默下载，退出后自动安装并重启。"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import httpx
from PySide6.QtCore import QObject, QThread, Signal

from desktop_shell.config import APP_VERSION, GITHUB_API


class UpdateChecker(QObject):
    """后台检查 GitHub Releases 是否有新版本。"""

    update_available = Signal(str, str)  # (version, download_url)
    check_complete = Signal()
    error = Signal(str)

    def __init__(self):
        super().__init__()
        self._thread: QThread | None = None

    def check(self) -> None:
        """启动后台检查。不会阻塞 UI。"""
        self._thread = QThread()
        worker = _CheckWorker(APP_VERSION, GITHUB_API)
        worker.moveToThread(self._thread)
        self._thread.started.connect(worker.run)
        worker.finished.connect(self._on_result)
        worker.finished.connect(self._thread.quit)
        worker.finished.connect(worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _on_result(self, result: dict) -> None:
        self._thread = None
        if result.get("update"):
            self.update_available.emit(result["version"], result["url"])
        self.check_complete.emit()


class _CheckWorker(QObject):
    finished = Signal(dict)

    def __init__(self, current_version: str, api_url: str):
        super().__init__()
        self._current = current_version
        self._api = api_url

    def run(self) -> None:
        try:
            with httpx.Client(timeout=httpx.Timeout(10.0, read=10.0)) as cli:
                r = cli.get(
                    f"{self._api}/releases/latest",
                    headers={"Accept": "application/vnd.github+json"},
                )
                if r.status_code != 200:
                    self.finished.emit({})
                    return
                release = r.json()
        except Exception:
            self.finished.emit({})
            return

        tag: str = release.get("tag_name", "")
        remote_ver = tag.lstrip("v")

        if _is_newer(self._current, remote_ver):
            url = ""
            for asset in release.get("assets", []):
                name: str = asset.get("name", "")
                if name.endswith(".exe") and "Setup" in name:
                    url = asset.get("browser_download_url", "")
                    break
            self.finished.emit({"update": True, "version": remote_ver, "url": url})
        else:
            self.finished.emit({})


def _is_newer(current: str, remote: str) -> bool:
    """比较两个 semver 字符串，remote > current 返回 True。"""
    try:
        cur = tuple(int(x) for x in current.split("."))
        rem = tuple(int(x) for x in remote.split("."))
        return rem > cur
    except (ValueError, AttributeError):
        return remote != current


def download_and_install(url: str, version: str, on_progress=None) -> None:
    """下载安装包，写批处理脚本（退出→安装→重启），启动后立即返回。

    调用方应在返回后退出应用，批处理会等待 2 秒后执行静默安装。
    """
    dest = Path(tempfile.gettempdir()) / f"Trading-Terminal-Setup-{version}.exe"

    # 1. 下载安装包
    with httpx.Client(timeout=httpx.Timeout(30.0, read=600.0)) as cli:
        with open(dest, "wb") as f:
            with cli.stream("GET", url) as r:
                total = int(r.headers.get("content-length", 0))
                downloaded = 0
                for chunk in r.iter_bytes(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if on_progress and total:
                        on_progress(downloaded, total)

    # 2. 写批处理脚本：等待主程序退出 → 静默安装 → 清理
    bat = dest.with_suffix(".bat")
    bat.write_text(
        f"@echo off\r\n"
        f"timeout /t 2 /nobreak >nul\r\n"
        f'start "" /wait "{dest}" /SILENT\r\n'
        f'del "{dest}"\r\n'
        f'del "%~f0"\r\n',
        encoding="gbk",
    )

    # 3. 脱离父进程启动批处理
    subprocess.Popen(
        [str(bat)],
        shell=True,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000008,  # DETACHED_PROCESS
        close_fds=True,
    )
