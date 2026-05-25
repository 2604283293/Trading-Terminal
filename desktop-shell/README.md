# 桌面主程序壳子 (desktop-shell)

PySide6 桌面应用主入口，承载三个业务模块的 Tab/窗口容器。

详见根目录 [ARCHITECTURE.md](../ARCHITECTURE.md)。

## 职责
- 主窗口、菜单、工具栏、状态栏
- 数据服务地址配置
- 三个模块的 Tab 切换 / 多窗口管理
- 全局快捷键、主题切换

## 技术栈
- PySide6（Qt 6 官方 Python 绑定）
- PyQt-Fluent-Widgets（现代化 UI 组件）
- httpx（调用共享数据服务）
