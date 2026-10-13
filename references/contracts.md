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

输出 `status: known|unknown`。unknown 的 delta 为 null，不返回差额明细；`reason` 说明首个未通过的检查，金额缺项一次列出所有缺失或 null 的金额字段，非法金额仅指出字段、不回显值。known 的 delta 为后车实付减前车实付（含全部费用），来源随结果返回。等于零表示同支出，不等同于应该加购。

known 还返回 `breakdown`，按 `subtotal, delivery_fee, other_fees, discount` 列出 `before, after, spend_change`（整数分）。`spend_change` 为该项对净支出的影响：费用增加为正，优惠增加为负，四项之和等于 delta。例如加购 1200 分、增加优惠 1000 分、费用不变，净支出增加 200 分。这是两份报价的算术分解，不证明某项费用变化由目标券造成。

## recommend

CLI 输入 `candidates` 列表，可选 `preference: {likes: [标签], dislikes: [标签]}`、`target_kcal`（用户设定的正整数）、`budget`（分）、`exclude_ids`（候选 ID 列表）。Python `recommend` 的最后一个可选参数也是 `exclude_ids`，保留原有 seed 参数位置。每个候选有 `id, quote, tags, constraints_checked: true`；主机应为同一候选维护稳定 ID。硬约束由主机根据用户要求和工具数据先核实，包括人数、预算、可售、忌口与规格；标记不是内核能独立证明的事实。

标签、likes/dislikes 和 exclude_ids 均为非空字符串组成的列表，可传空列表。preference 须是对象，缺省或 null 表示未设置；likes/dislikes 的显式 null 或错误类型拒绝整个请求，不默默忽略用户限制。exclude_ids 缺省或 null 表示未设置，其他非列表类型拒绝整个请求。候选自身 tags 格式错误只排除该候选。标签按原字符串精确匹配，来自菜单说明；likes/dislikes 仅来自用户主动反馈。**命中 dislikes 的候选直接排除**，即使同一标签也在 likes 中。标签未命中不证明没有过敏原，仍须主机核实忌口证据。

`exclude_ids` 从所有榜单及随机池中移除相应候选。用户说“再换一个”时，主机把本轮已展示的 ID 累积传入；内核不保存历史。随机仍在过滤后的钱包榜单中等概率抽取。候选耗尽返回空榜单及 random=null，解释排除原因，等用户调整条件或明确重新开始，不自动清空排除列表或放宽预算。

可选 `nutrition`：`source, tool: list-nutrition-foods, response_ref, cart_digest: digest(quote.cart), kcal, protein_g`。仅完整匹配份量、规格和组合的值才能填；无法对应整车的营养为 null，不以同名其他规格替代。营养目标排序按与用户能量目标的绝对差，不称「最健康」。缺目标时 nutrition=null，缺营养候选单列 nutrition_unknown。

输出保留三种排序、random、excluded（数量）及 nutrition_unknown，并增加：

- `excluded_details: [{index, reason}]`：index 是输入 candidates 的零基下标，reason 是该候选首个失败检查，例如缺费用、超预算、命中不喜欢标签、已展示或上下文不同；格式错误不回显原始输入。
- 每张卡保留 id、total、kcal、protein_g、taste_score、source，并带门店、方式、预约时段、币种、商品规格数量、应用券、报价引用与观测/失效时间；`includes_all_fees=true` 表示通过本地完整报价校验。
- `matched_likes` 是去重排序后的喜好匹配标签，taste_score 为其数量；`budget_remaining` 是预算减实付，未设预算为 null；`kcal_distance` 是与用户热量目标的绝对差，缺目标或缺营养为 null。

主机用这些字段解释每种选择，不把不同候选之间的价差说成同车用券节省。营养目标是排序偏好，不是热量上限。排序卡片不包含完整 Quote，创建订单仍须提供原始完整报价并走交易闸门。

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
