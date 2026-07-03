graphify 离线安装器
===================

适用环境：Windows 10（1803 及以上）桌面云机器，无公网，但公司内网可访问
PyPI 代理：http://192.168.21.14:25000/pypi/repository/pypi-all/simple

────────────────────────
安装步骤
────────────────────────

1. 解压本 zip 到任意目录，例如 D:\graphify\
2. 进入解压目录，双击 install.bat
3. 等待 30-60 秒：脚本会自动检测 Python、配置内网 PyPI 代理、
   安装 graphifyy、把 SKILL.md 部署到 Claude Code 的 skills 目录
4. 安装完成。新开一个 cmd 窗口，输入 `graphify --version` 验证

────────────────────────
常见问题
────────────────────────

Q: 没有 Python 可以装吗？
A: 可以。本 zip 自带 Python 3.12 embeddable，install.bat 会自动使用。

Q: 安装失败怎么办？
A: 检查内网 PyPI 代理是否可达：http://192.168.21.14:25000/pypi/repository/pypi-all/simple
   截图报错信息联系 IT。

Q: 如何换装到 Codex / OpenCode / Cursor？
A: 编辑 install.bat，把最后一行的 `graphify install claude` 改成
   `graphify install codex`（或 opencode / cursor 等），重新双击。

Q: 如何卸载？
A: 双击 uninstall.bat。

────────────────────────
内网 PyPI 代理配置（构建时注入）
────────────────────────

  index-url:      http://192.168.21.14:25000/pypi/repository/pypi-all/simple
  trusted-host:   192.168.21.14
  timeout:        6000 秒