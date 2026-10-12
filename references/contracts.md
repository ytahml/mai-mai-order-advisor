# 内部数据契约

此文件定义项目自己的标准化输入，**不是官方 Tool Schema**。官方当前 tools/list 与响应决定字段映射；MVP 没有固定官方参数适配器。Python 模块无网络、无状态存储、无 Token。通过 `from copilot.core import compare, recommend, digest` 与 `from copilot.workflow import initial, transition` 调用，或 `python3 -m copilot compare|recommend|transition` 从 stdin 传 JSON。CLI 用系统当前时间；演示和 Python 测试可注入模拟时间。stdout 不应归档真实输入/输出。

## Quote

| 字段 | 约束 |
| --- | --- |
| source | `tool`（真实响应）或 `fixture`（模拟） |
| tool / response_ref | `calculate-price` / 当前会话响应引用；不是用户账号 |
| store / store_name | 门店标识与名称 |
| mode / fulfillment_ref / time_slot | 工具已确认的取餐方式、目的地/履约选择的不透明会话引用、预约时段；修改任何履约信息须改变引用 |
| currency | 仅 `CNY` |
| cart | 非空列表，每行 `sku, variant, name, quantity`；variant 必须包含套餐替换/特制等完整选择的稳定标识；相同 sku+variant 合并数量 |
| subtotal / delivery_fee / other_fees / discount / total | 官方明确金额，转换成非负整数分；所有费用齐全；总价必须算术一致，布尔值/浮点/缺项均拒绝 |
| coupons | 官方实际应用的券标识列表；无券也必须明确 `[]` |
| observed_at / expires_at | 秒级 Unix 时间，`observed_at <= now < expires_at`；最长 300 秒。expires_at 是本地安全上限与官方有效期取较早者，不声称官方保证五分钟有效 |

两份报价须同来源、同履约上下文且采样相隔不超过 120 秒。不可把 tool 字段手工贴到猜测金额上；source 和 response_ref 是主机维护的来源证据，不是签名认证。

## compare

CLI 输入：`{"before": Quote, "after": Quote, "kind": "same_cart" | "top_up", "evidence": CouponEvidence}`。

`same_cart` 要求两车商品规格数量完全一致。`top_up` 要求原车是加购车严格子集，并提供以下 CouponEvidence：

- `source` 与报价相同，`tool` 是 query-store-coupons / query-my-coupons / available-coupons，`response_ref` 指向实际响应。
- `coupon` 是加购车实际应用的券；`threshold` 是官方门槛（整数分），`conditions` 是工具给出的适用条件；`conditions_known: true` 表示所有适用条件已核实。
- `before_eligible` 必须是明确布尔值，`after_eligible` 必须 true。两车资格依据工具返回的适用范围、时间、门店及报价确定；仅知道券面金额、营销标题或简单相加达到门槛还不够。
- `before_quote` / `after_quote` 分别为 `digest(完整 Quote)`，避免资格证据串车。

输出 `status: known|unknown`。unknown 的 delta 为 null；known 的 delta 为后车实付减前车实付（含全部费用），来源随结果返回。等于零表示同支出，不等同于应该加购。

## recommend

CLI 输入 `candidates` 列表，可选 `preference: {likes: [标签], dislikes: [标签]}`、`target_kcal`（用户设定的正整数）、`budget`（分）。每个候选有 `id, quote, tags, constraints_checked: true`。硬约束由主机根据用户要求和工具数据先核实，包括人数、预算、可售、忌口与规格；标记不是内核能独立证明的事实。

可选 `nutrition`：`source, tool: list-nutrition-foods, response_ref, cart_digest: digest(quote.cart), kcal, protein_g`。仅完整匹配份量、规格和组合的值才能填；无法对应整车的营养为 null，不以同名其他规格替代。营养目标排序按与用户能量目标的绝对差，不称「最健康」。缺目标时 nutrition=null，缺营养候选单列 nutrition_unknown。口味标签来自菜单说明，likes/dislikes 仅来自用户主动反馈。输出包括三种排序、随机选择与排除数量；不宣称不同候选之间是同车优惠。

## 交易状态机

Python：`transition(state, event, now)`；CLI：`{"state": 上次返回state, "event": {...}}`（首次可省 state）。返回 `state, intent`，有时含 `prompt, summary, may_show_payment_link`。prompt 是用户需亲自确认的完整口令，包含本次 challenge；真实运行不能程序自动代填。demo 的自动确认只用于显著标记的 fixture。

| action / 前置状态 | event 字段 | 结果 |
| --- | --- | --- |
| offer_coupons / browsing | source | 全量领券确认口令 |
| confirm_coupons / coupon_confirmation | confirmation=用户输入口令 | 一次 auto-bind-coupons 意图；五分钟过期 |
| coupon_result / coupon_in_flight | 无；不论成功/超时均执行 | refresh_required |
| refreshed / refresh_required | wallet_response_ref, wallet_observed_at, quote | 卡包在领券结果后刷新、再报价 → browsing |
| offer_order / browsing 或未发出的订单确认 | quote, payload_digest | 展示 summary 和确认口令；旧确认作废 |
| confirm_order / order_confirmation | confirmation=用户输入口令 | order_ready |
| dispatch_order / order_ready | quote, payload_digest | 完全匹配且有效才输出一次 create-order 意图 |
| create_result / order_in_flight | order_ref（可缺） | 有引用给 query-order 读意图；无引用留待人工核实 |
| verified / verify_required | source, tool=query-order, response_ref, order_ref, matches_summary, total, status | 读回匹配后 pending_payment 或 paid；否则 status_unknown |
| reset / browsing 或尚未发出的确认 | 无 | 撤销本地意图，不取消真实订单 |

刷新要求 `completed_at < wallet_observed_at <= quote.observed_at <= now`。秒级时间无法区分同秒先后，因此即使响应引用不同，同秒刷新也拒绝。主机记录 `coupon_result` 后，等本地时钟进入下一秒再查询卡包，随后重新报价；保留实际观测时间，不能给旧响应改时间戳。仅重复只读查询，不重试领券。

`payload_digest = digest(实际 create-order 参数对象)`。该摘要涵盖地址引用、餐具、预约、备注等所有实际参数。确认时主机必须展示与这些参数一致的人可读摘要；引用不能代替面向用户的具体配送选择。`matches_summary` 是主机逐项核对商品、门店、履约和券后填入，不能只比总价。状态不允许重放、回滚、并行分支；异常输出不会授权任何动作。

**保证边界**：这是协作式状态机。伪造 state、伪造来源或让助手伪造用户输入都能绕过应用约定；本库不充当权限服务。主机维护可信用户事件、原子保存最新内存 state 后才发工具调用、校验当前 Schema/参数摘要、启用写工具审批。项目不提供可防篡改交易代理，也不对跨会话崩溃恢复作保证；会话丢失且可能已写入时先人工核实，不能重放。
