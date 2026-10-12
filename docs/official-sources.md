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

当日后续已在主机核对部分运行时工具 Schema，并执行到店自取的门店、菜单、详情、营养和真实试价。费用字段缺省语义仍未核实，没有执行真实写工具；内部 fixture 全部合成。

## 费用字段核查（2026-10-12）

- [官方仓库固定版本](https://github.com/M-China/mcd-mcp-server/blob/e90ecc5c918f307ff5f997caa73e4d60bef375e9/README.md)：版本日志到 1.0.9；价格工具简介未定义缺失、null 或默认零的含义。仓库文件树只有中英文 README，没有可核查的服务端实现。
- [官方历史价格示例](https://github.com/M-China/mcd-mcp-server/blob/d013f797be315edeab55e889cceecf6974f15a94/README.md#L410-L459)：有配送费示例，无打包费及餐具费缺省规则。旧示例不能证明当前接口的默认值。
- [官网接入指南](https://open.mcd.cn/mcp/doc) 4.2.10：浏览抓取超时后，经公开 HTML 引用的前端资源读取内嵌文档。当前资源为 [index.42407507.025ffc2e.chunk.js](https://open.mcd.cn/static/js/index.42407507.025ffc2e.chunk.js)。文档包含 `needTableware` 和餐具费示例，未说明 `packingPrice` 或费用省略语义；示例数值不能同时满足本项目的全费用加总公式。
- 官网提供的 [guide.md](https://open.mcd.cn/mcp/guide.md) 是精简接入说明，未提供上述字段的缺省定义。对官方仓库文档、历史文档和 issues 的检索也未找到该规则；没有官方人员的新回复或非公开服务端代码可供确认。

结论：目前只能确认费用字段可能未提供，不能证明未提供就是零。公开资料不足以授权放宽报价校验。运行时字段可选性来自当日成功联调时的 Schema，仅适用于当时观测；后续回合工具未暴露，未重新取得 Schema 或报价。工具未暴露不代表服务断连，连接状态原因尚未查明。真实请求、原始响应、门店/餐品标识和追踪标识未保存到项目；后续按用户要求仅在验收记录保留套餐名称、返回总价和营养的摘要。

后续经用户授权备份并修正主机认证环境变量引用后，新启动的 Codex 后端成功发现 11 个只读工具；依据新 Schema，在临时只读校验进程中重跑了官方接口。当前聊天的工具目录最初仍缓存旧状态；随后 11 个内置工具恢复，通过内置时间查询和再次试价确认本聊天连接也已恢复。费用缺省语义仍未知，详见 [最新验收](validation.md#认证修正后的只读复验)。
