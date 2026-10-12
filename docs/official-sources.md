# 官方资料与获取记录

核对日期：2026-10-12。仅查阅官方公开仓库，无账号数据。

| 来源 | 本轮确认范围 |
| --- | --- |
| [MCP README](https://github.com/M-China/mcd-mcp-server) | 连接地址、Streamable HTTP/Bearer、公开工具清单包含 `order-list`；版本日志最新记录为 1.0.9（2026-09-10），未公开完整 JSON Schema |
| [赛事 README](https://github.com/M-China/mcd-developer-innovation-challenge) | 必备文件、声明不可改、WorkBuddy 专项材料的可选范围 |
| [声明原始文本](https://raw.githubusercontent.com/M-China/mcd-developer-innovation-challenge/main/CONTEST_DECLARATION.md) | 浏览工具返回 text/plain 的全部 22 行，逐行原文复制到根目录 CONTEST_DECLARATION.md，无添加或改写 |

本地曾有一处段间空行与官方原文不一致。2026-10-12 重新从 raw URL 下载后，已逐字节与本地文件比较一致（`cmp` 通过）；本地 SHA-256 为 `cd28101bcb29cc8fb24b372fe91ce6b42c4a1487a54e01f7ade0c8c6a84241b7`。

因此声明当前与官方 raw 文本逐字节一致；`scripts/check_project.py` 用本地 SHA-256 防止误改，但不固定远端版本。公开报名时应再次核对官方当前原文件；不要在声明内添加项目说明、个人资料或签名。

声明原文虽已逐字节核对，参赛者仍需自行阅读并确认规则中的授权与责任内容。用户已授权创建公开项目仓库并推送代码；这不等于代用户提交报名 Issue 或确认本人声明。

未连接实时 MCP，未执行 tools/list、真实只读报价或任何真实写工具。当前参数、输出字段及状态枚举尚待主机现场核验；内部 fixture 全部合成。
