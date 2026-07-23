## Troubleshooting

### Windows support

Use CPython 3.10 or 3.12 on native Windows x86_64 and install Graphify normally with pip or uv. The exact public `helix-db-embedded` version must provide a `win_amd64` wheel; do not substitute WSL, a source build, a downloaded DLL, or a compatibility graph library.

### PowerShell 5.1: Vertical scrolling stops working

Use Windows Terminal or PowerShell 7 when possible. Graphify does not patch terminal modes or load a helper DLL.

---
