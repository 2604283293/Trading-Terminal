"""需求反馈 Tab — 提交 issue 到 GitHub，展示已提交反馈列表。"""
from __future__ import annotations

import platform
from datetime import datetime

import httpx
from PySide6.QtCore import QObject, QThread, Qt, Signal, QTimer
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from desktop_shell.config import APP_VERSION, GITHUB_API, get_github_token
from desktop_shell.feedback_queue import dequeue_all, enqueue, pending_count

FEEDBACK_TYPES = {
    "bug": ("Bug 反馈", "bug"),
    "feature": ("功能建议", "enhancement"),
    "data": ("数据问题", "data-issue"),
    "other": ("其他", "question"),
}


class FeedbackWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._submit_thread: QThread | None = None
        self._build_ui()

        # 离线队列自动重试
        self._retry_timer = QTimer(self)
        self._retry_timer.timeout.connect(self._flush_queue)
        self._retry_timer.start(60_000)

        # 首次加载已有反馈
        QTimer.singleShot(500, self._load_my_feedback)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # ── 标题 ──
        title = QLabel("需求反馈")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        hint = QLabel("发现 Bug 或有功能需求？填写下方表单，我们将及时处理。")
        hint.setStyleSheet("color: #888; font-size: 12px; margin-bottom: 4px;")
        layout.addWidget(hint)

        # ── 表单 ──
        form = QWidget()
        form.setStyleSheet(
            "QWidget { background: #2b2b2b; border: 1px solid #3a3a3a; "
            "border-radius: 8px; padding: 16px; }"
        )
        form_layout = QVBoxLayout(form)
        form_layout.setSpacing(10)

        # 类型 + 联系方式
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("类型:"))
        self._type_combo = QComboBox()
        for key, (label, _) in FEEDBACK_TYPES.items():
            self._type_combo.addItem(label, key)
        row1.addWidget(self._type_combo)
        row1.addSpacing(20)
        row1.addWidget(QLabel("联系方式(选填):"))
        self._contact = QLineEdit()
        self._contact.setPlaceholderText("微信/邮箱，方便我们跟进")
        row1.addWidget(self._contact, stretch=1)
        form_layout.addLayout(row1)

        # 标题
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("标题:"))
        self._title = QLineEdit()
        self._title.setPlaceholderText("简要描述你的问题或建议（必填）")
        row2.addWidget(self._title, stretch=1)
        form_layout.addLayout(row2)

        # 描述
        form_layout.addWidget(QLabel("详细描述（至少10个字）:"))
        self._desc = QPlainTextEdit()
        self._desc.setPlaceholderText("请描述：\n1. 具体问题或需求\n2. 期望的结果\n3. 复现步骤（如适用）")
        self._desc.setMinimumHeight(100)
        self._desc.setStyleSheet(
            "QPlainTextEdit { border: 1px solid #3a3a3a; border-radius: 4px; padding: 8px; "
            "font-size: 13px; }"
        )
        form_layout.addWidget(self._desc)

        # 按钮 + 状态
        btn_row = QHBoxLayout()
        self._submit_btn = QPushButton("提交反馈")
        self._submit_btn.setStyleSheet(
            "QPushButton { background: #d83a3a; color: white; font-weight: bold; "
            "padding: 8px 24px; border-radius: 4px; }"
            "QPushButton:hover { background: #c13030; }"
            "QPushButton:disabled { background: #555; }"
        )
        self._submit_btn.clicked.connect(self._on_submit)
        btn_row.addWidget(self._submit_btn)

        self._status = QLabel("")
        self._status.setStyleSheet("color: #888; font-size: 12px; border: none;")
        btn_row.addWidget(self._status)
        btn_row.addStretch()

        queue_count = pending_count()
        if queue_count:
            self._status.setText(f"有 {queue_count} 条反馈待提交（等待网络恢复）")
        form_layout.addLayout(btn_row)
        layout.addWidget(form)

        # ── 我的反馈 ──
        layout.addWidget(QLabel("我的反馈历史"))
        self._feedback_table = QTableWidget()
        self._feedback_table.setColumnCount(4)
        self._feedback_table.setHorizontalHeaderLabels(["标题", "类型", "状态", "创建时间"])
        self._feedback_table.setAlternatingRowColors(True)
        self._feedback_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._feedback_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._feedback_table.verticalHeader().setVisible(False)
        hdr = self._feedback_table.horizontalHeader()
        hdr.setStretchLastSection(True)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._feedback_table.doubleClicked.connect(self._on_open_issue)
        self._feedback_table.setMaximumHeight(200)
        layout.addWidget(self._feedback_table)

        layout.addStretch()

    def _on_submit(self):
        title_text = self._title.text().strip()
        desc_text = self._desc.toPlainText().strip()
        ftype = self._type_combo.currentData()

        if not title_text:
            self._status.setText("请填写标题")
            self._status.setStyleSheet("color: #d83a3a; font-size: 12px; border: none;")
            return
        if len(desc_text) < 10:
            self._status.setText("描述至少 10 个字")
            self._status.setStyleSheet("color: #d83a3a; font-size: 12px; border: none;")
            return

        self._submit_btn.setEnabled(False)
        self._submit_btn.setText("提交中…")
        self._status.setText("正在提交…")
        self._status.setStyleSheet("color: #e8870a; font-size: 12px; border: none;")

        label = FEEDBACK_TYPES[ftype][1]
        body = f"""## 客户端反馈

**类型**: {FEEDBACK_TYPES[ftype][0]}
**联系方式**: {self._contact.text().strip() or '未提供'}
**应用版本**: {APP_VERSION}
**操作系统**: {platform.platform()}
**提交时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

{desc_text}
"""

        self._submit_thread = QThread()
        worker = _SubmitWorker(title_text, body, label, GITHUB_API, get_github_token())
        worker.moveToThread(self._submit_thread)
        self._submit_thread.started.connect(worker.run)
        worker.finished.connect(self._on_submit_done)
        worker.finished.connect(self._submit_thread.quit)
        worker.finished.connect(worker.deleteLater)
        self._submit_thread.finished.connect(self._submit_thread.deleteLater)
        self._submit_thread.start()

    def _on_submit_done(self, result: dict) -> None:
        self._submit_btn.setEnabled(True)
        self._submit_btn.setText("提交反馈")
        self._submit_thread = None

        if result.get("success"):
            self._status.setText("反馈已提交，感谢！")
            self._status.setStyleSheet("color: #2e9f3e; font-size: 12px; border: none;")
            self._title.clear()
            self._desc.clear()
            self._contact.clear()
            QTimer.singleShot(1000, self._load_my_feedback)
        else:
            error = result.get("error", "未知错误")
            if result.get("queued"):
                self._status.setText(f"已保存到本地，将在网络恢复后提交")
            else:
                self._status.setText(f"提交失败: {error[:80]}")
            self._status.setStyleSheet("color: #d83a3a; font-size: 12px; border: none;")

    def _flush_queue(self):
        """尝试提交离线队列中的反馈。"""
        items = dequeue_all()
        if not items:
            return
        for item in items:
            # 使用同步提交（不阻塞 UI，因为 item 很少）
            try:
                self._do_sync_submit(item)
            except Exception:
                # 仍然失败则放回队列
                enqueue(item)

        if pending_count() == 0:
            self._status.setText("")
        self._load_my_feedback()

    def _do_sync_submit(self, item: dict) -> None:
        token = get_github_token()
        if not token:
            raise RuntimeError("No token")
        with httpx.Client(timeout=httpx.Timeout(10.0, read=15.0)) as cli:
            r = cli.post(
                f"{GITHUB_API}/issues",
                json={
                    "title": item["title"],
                    "body": item["body"],
                    "labels": [item["label"], "user-feedback"],
                },
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
            )
            r.raise_for_status()

    def _load_my_feedback(self):
        """加载已提交的反馈列表。"""
        token = get_github_token()
        if not token:
            self._feedback_table.setRowCount(1)
            self._feedback_table.setItem(0, 0, QTableWidgetItem("未配置 GitHub Token，无法加载反馈"))
            return

        try:
            with httpx.Client(timeout=httpx.Timeout(8.0, read=10.0)) as cli:
                r = cli.get(
                    f"{GITHUB_API}/issues",
                    params={"state": "all", "labels": "user-feedback", "per_page": 50},
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/vnd.github+json",
                    },
                )
                r.raise_for_status()
                issues = r.json()
        except Exception:
            self._feedback_table.setRowCount(1)
            self._feedback_table.setItem(0, 0, QTableWidgetItem("加载失败（网络不可用）"))
            return

        self._feedback_table.setRowCount(len(issues))
        for i, issue in enumerate(issues):
            title = QTableWidgetItem(issue.get("title", ""))
            title.setData(Qt.ItemDataRole.UserRole, issue.get("html_url", ""))
            self._feedback_table.setItem(i, 0, title)

            labels = [lb["name"] for lb in issue.get("labels", [])]
            type_label = next((lb for lb in labels if lb != "user-feedback"), "")

            type_item = QTableWidgetItem(type_label)
            type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._feedback_table.setItem(i, 1, type_item)

            state = issue.get("state", "open")
            state_item = QTableWidgetItem("已关闭" if state == "closed" else "处理中")
            state_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if state == "closed":
                state_item.setForeground(Qt.GlobalColor.gray)
            else:
                state_item.setForeground(Qt.GlobalColor.darkGreen)
            self._feedback_table.setItem(i, 2, state_item)

            created = issue.get("created_at", "")[:10]
            time_item = QTableWidgetItem(created)
            time_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._feedback_table.setItem(i, 3, time_item)

    def _on_open_issue(self, index):
        url = self._feedback_table.item(index.row(), 0).data(Qt.ItemDataRole.UserRole)
        if url:
            QDesktopServices.openUrl(url)


class _SubmitWorker(QObject):
    finished = Signal(dict)

    def __init__(self, title: str, body: str, label: str, api_url: str, token: str):
        super().__init__()
        self._title = title
        self._body = body
        self._label = label
        self._api = api_url
        self._token = token

    def run(self) -> None:
        if not self._token:
            # 无 token → 离线队列
            enqueue({
                "title": self._title,
                "body": self._body,
                "label": self._label,
            })
            self.finished.emit({"success": False, "error": "无 Token", "queued": True})
            return

        try:
            with httpx.Client(timeout=httpx.Timeout(10.0, read=15.0)) as cli:
                r = cli.post(
                    f"{self._api}/issues",
                    json={
                        "title": self._title,
                        "body": self._body,
                        "labels": [self._label, "user-feedback"],
                    },
                    headers={
                        "Authorization": f"Bearer {self._token}",
                        "Accept": "application/vnd.github+json",
                    },
                )
                r.raise_for_status()
            self.finished.emit({"success": True})
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:200] if exc.response is not None else str(exc)
            # 可重试的错误 → 离线队列
            enqueue({
                "title": self._title,
                "body": self._body,
                "label": self._label,
            })
            self.finished.emit({"success": False, "error": detail, "queued": True})
        except Exception as exc:
            enqueue({
                "title": self._title,
                "body": self._body,
                "label": self._label,
            })
            self.finished.emit({"success": False, "error": str(exc), "queued": True})
