# 核心重构设计文档：《发疯华尔街：混沌微观实体引擎》
**(Chaos Entity Market Engine - Version 2.0)**

## 0. 引擎重构愿景 (Vision)
本次重构将彻底废弃“静态流动性+线性公式”的旧模型，打造一个**“活着的、有情绪的、多方实体博弈”**的深海生态系统：
1. **价格不是算出来的，是买卖砸出来的**：采用 AMM 非线性滑点公式，资金量越大，价格冲击呈指数级爆炸。
2. **流动性是活的流体**：极度恐慌时盘口资金撤退，流动性干涸，少量的抛单就能引发无底洞般的暴跌。
3. **AI 实体下场博弈**：量化基金、做空秃鹫、价值投行作为独立实体（有资金池、有持仓、有爆仓线）在后台自动交易。
4. **注意力核弹**：名人和玩家的“随口一句话（无意行为）”，会转化为散户情绪，引发全网跟风与市场踩踏。

---

## 1. 数据库 Schema 重构设计 (The World State)

为支持实体博弈与混沌情绪，需要对数据库进行以下扩展：

### 1.1 升级 `Stock` 表 (股票情绪与流动性)
| 新增/修改字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `base_liquidity` | REAL | 基准流动性池（正常状态下的承载力） |
| `current_liquidity` | REAL | 当前实际流动性（受恐慌指数影响，动态收缩） |
| `retail_sentiment` | REAL | 散户情绪指数 (-1.0 到 1.0)，每回合向0自然衰减 |
| `volatility_index` | REAL | 个股恐慌指数 (0.0 到 1.0)，决定流动性抽干的程度 |

### 1.2 升级 `NPC` 表 (跨界名流与影响力)
*将原 `CompanyNPC` 升级为全局 NPC 表。*
| 新增字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `company_id` | INTEGER | 可为 NULL。NULL 表示独立大V/政客 |
| `npc_type` | TEXT | `executive` (高管), `celebrity` (名流), `politician` (政客) |
| `influence_power` | INTEGER | 0-100。决定其言论对 `retail_sentiment` 的核弹级影响力 |

### 1.3 新增 `Institution` 与 `InstitutionPosition` 表 (AI 机构实体)
| 表名 | 字段 | 类型 | 说明 |
| :--- | :--- | :--- | :--- |
| **Institution** | `inst_id` | INTEGER PK | - |
| | `name` | TEXT | 机构名称 (如 "文艺复兴量化", "浑水做空") |
| | `type` | TEXT | `value` (价值), `hedge_short` (做空), `quant` (量化) |
| | `capital` | REAL | 可用现金池 |
| | `risk_tolerance`| REAL | 风险偏好 (0.1~1.0)，决定其止损线有多深 |
| | `status` | TEXT | `active`, `bankrupt` (破产机构将被清算) |
| **InstPosition** | `inst_id` | INTEGER FK | - |
| | `stock_id` | INTEGER FK | - |
| | `position_type` | TEXT | `long` (做多) / `short` (做空) |
| | `volume_usd` | REAL | 持仓成本市值 |

### 1.4 新增 `MarketTrace` 表 (市场痕迹与情报簿)
用于记录后台 AI 实体的动作，供 LLM 播报或玩家刺探。
| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `trace_id` | INTEGER PK | - |
| `turn` | INTEGER | 发生回合 |
| `stock_id` | INTEGER FK | 关联股票 |
| `trace_type` | TEXT | `broadcast` (全网皆知的大新闻), `rumor` (暗网/圈内私密传言) |
| `content` | TEXT | 事件描述 (如："神秘巨资在周三扫货 5000 万") |

---

## 2. 核心计算管线：五阶段混沌结算 (The 5-Phase Pipeline)

在 `market_engine.py` 的回合结算中，必须严格按照以下 5 个阶段执行：

### Phase 1: 注意力溢出与名人发癫 (Attention Spillovers)
*   **玩家无意行为**：LLM 捕获玩家闲聊中的公司评价，提交 `spillover_ap`，直接转化为 `retail_sentiment` 的剧烈波动。
*   **名人随机发推**：引擎按概率随机抽取一名高影响力 `celebrity` 发表情绪言论，产生 `broadcast` 痕迹，并大幅修改目标股票情绪。

### Phase 2: 机构 AI 独立决策 (Institutional Actors)
遍历所有活跃机构，根据其 `type` 执行资金流（Flow）注入：
*   **Value (价值)**：股价远低于基本面时买入。浮亏超 30% 触发绝望止损（大额卖单）。
*   **Quant (量化)**：不看基本面，只看 `retail_sentiment` 为正且在涨，高频追涨杀跌。
*   **Short (做空)**：专盯 `scandal_risk` 高或被负面舆论攻击的股票，建立空头头寸。建仓极度隐蔽 (`rumor`)，建仓完毕后可能发布做空报告 (`broadcast`) 砸盘。

### Phase 3: 流动性干涸与散户汇流 (Liquidity Vacuum)
*   **恐慌指数计算**：基于上回合涨跌幅和暴雷风险。
*   **流动性抽干**：恐慌时，`current_liquidity = base_liquidity * (1.0 - volatility_index * 0.8)`。最极端时盘口只剩 20% 资金承接。
*   **散户合流**：计算散户的无脑跟风资金量（受情绪指数驱动）。

### Phase 4: 非线性滑点价格爆炸 (Non-linear Slippage)
*   将所有资金净额相加：`Total_Net_Flow = Player_Flow + Inst_Flow + Retail_Flow`
*   使用**指数滑点公式**计算冲击力。吃透流动性时，价格涨跌幅呈指数放大。

### Phase 5: 级联清算与痕迹归档 (Cascading Liquidations)
*   检查玩家和机构是否亏穿底线触发 **Margin Call (爆仓)**。
*   如果某做空机构爆仓，它必须**强制买入 (buy_to_cover)** 大量股票，这将在下一回合引发史诗级逼空 (Short Squeeze)。
*   将本回合生成的 `MarketTrace` 归档，供下回合 LLM 阅读。

---

## 3. 核心伪代码实现蓝图 (Pseudo-code for LLM Coder)

请 AI 编码助手严格参考以下 Python 伪代码结构重写 `market_engine.py`：

```python
import math
import random

# --- 引擎常量设定 ---
RETAIL_POWER = 0.05      # 散户情绪转化资金的乘数
SLIPPAGE_EXPONENT = 1.3  # 滑点指数 (1.0为线性，>1.0为非线性爆炸)
DECAY_RATE = 0.8         # 情绪每回合向 0 的自然衰减率

def settle_market_turn(conn, player_actions, spillover_events, macro_events, current_turn):
    
    traces = [] # 收集本回合的 MarketTrace

    # ==========================================
    # Phase 1: 注意力溢出与名人发癫 (Spillovers)
    # ==========================================
    
    # 1.1 处理玩家随口言论的蝴蝶效应 (由 LLM 通过 spillover_ap 提交)
    for event in spillover_events:
        impact = event['sentiment_shift'] * (get_player_fame(conn) / 100.0)
        update_stock_retail_sentiment(conn, event['stock_id'], impact)
        traces.append(create_trace(event['stock_id'], "rumor", "市场传言某位业界巨头私下极度看衰/看好该公司。"))

    # 1.2 名人随机事件
    celebrities = get_all_celebrities(conn)
    for celeb in celebrities:
        if random.random() < 0.05: # 5% 概率触发
            target_stock = random.choice(get_all_stocks(conn))
            sentiment_impact = random.uniform(-1.0, 1.0) * (celeb.influence_power / 100.0)
            update_stock_retail_sentiment(conn, target_stock.id, sentiment_impact)
            traces.append(create_trace(target_stock.id, "broadcast", f"突发！大V {celeb.name} 在社交媒体上对 {target_stock.name} 发表了极端言论！"))

    # ==========================================
    # Phase 2: 机构实体独立决策 (Institutional Flows)
    # ==========================================
    institutions = get_active_institutions(conn)
    inst_flows = {stock.id: 0.0 for stock in get_all_stocks(conn)} # 记录每只股票的机构净流入
    
    for inst in institutions:
        for stock in get_all_stocks(conn):
            flow = 0.0
            # A. 价值基金：低估买入，跌穿止损线恐慌抛售
            if inst.type == 'value':
                price_gap = (stock.fundamental_value - stock.current_price) / stock.current_price
                if price_gap > 0.2: # 严重低估
                    flow = inst.capital * 0.1 
                    traces.append(create_trace(stock.id, "rumor", f"{inst.name} 似乎正在场外悄悄吸筹。"))
                # 检查止损
                if check_inst_loss(inst, stock) < -0.3 * inst.risk_tolerance:
                    flow = -get_inst_position_value(inst, stock) # 全部清仓认赔
                    traces.append(create_trace(stock.id, "broadcast", f"惨烈！{inst.name} 无法承受亏损，挥泪斩仓 {stock.name}！"))

            # B. 做空秃鹫：盯紧暴雷风险
            elif inst.type == 'hedge_short':
                if stock.scandal_risk > 80:
                    flow = -inst.capital * 0.15 # 建立空头头寸
                    if random.random() < 0.2: # 20% 概率发布做空报告
                        update_stock_retail_sentiment(conn, stock.id, -0.8) # 散户直接吓崩
                        traces.append(create_trace(stock.id, "broadcast", f"【做空狙击】{inst.name} 发布长达50页报告，指控 {stock.name} 财务造假！"))
                    else:
                        traces.append(create_trace(stock.id, "rumor", f"暗网数据显示，有神秘对冲基金借入了海量 {stock.name} 的股票。"))

            # C. 量化动量：无脑追逐情绪
            elif inst.type == 'quant':
                if stock.retail_sentiment > 0.3:
                    flow = inst.capital * 0.2
                elif stock.retail_sentiment < -0.3:
                    flow = -inst.capital * 0.2

            # 汇总该机构的操作并更新其可用资金/持仓
            inst_flows[stock.id] += flow
            execute_inst_trade(conn, inst, stock, flow)

    # ==========================================
    # Phase 3 & 4: 流动性干涸与非线性滑点 (Liquidity & AMM Math)
    # ==========================================
    for stock in get_all_stocks(conn):
        
        # 3.1 散户无脑情绪流
        retail_flow = stock.retail_sentiment * stock.base_liquidity * RETAIL_POWER
        
        # 3.2 汇总所有资金 (含玩家本回合的交易额)
        player_flow = get_player_net_trade(player_actions, stock.id)
        total_net_flow = retail_flow + inst_flows[stock.id] + player_flow
        
        # 3.3 计算恐慌引发的流动性干涸
        volatility = min(1.0, stock.scandal_risk / 100.0 + abs(stock.retail_sentiment) * 0.5)
        current_liquidity = max(stock.base_liquidity * 0.1, stock.base_liquidity * (1.0 - volatility * 0.8)) # 最少剩 10% 流动性
        
        # 4.1 核心公式：非线性指数滑点冲击
        # (资金差额 / 当前盘口深度) ^ 滑点指数
        flow_ratio = abs(total_net_flow) / current_liquidity
        flow_ratio = min(flow_ratio, 2.5) # 钳制防止单局溢出 (限制最大单次绝对冲击幅度)
        
        price_impact_pct = math.copysign(math.pow(flow_ratio, SLIPPAGE_EXPONENT), total_net_flow)
        
        # 叠加宏观黑天鹅事件乘数
        macro_multiplier = get_macro_multiplier(macro_events, stock.industry_tag)
        new_price = max(0.01, round(stock.current_price * (1.0 + price_impact_pct) * macro_multiplier, 2))
        
        # 状态向 0 衰减归位
        new_sentiment = stock.retail_sentiment * DECAY_RATE
        save_stock_state(conn, stock.id, new_price, new_sentiment, current_liquidity)

    # ==========================================
    # Phase 5: 破产与级联清算 (Cascading Bankruptcies)
    # ==========================================
    # 检查所有机构是否亏光本金
    for inst in institutions:
        if calculate_inst_net_worth(conn, inst) < 0:
            set_inst_bankrupt(conn, inst)
            traces.append(create_trace(None, "broadcast", f"【金融核弹】顶级机构 {inst.name} 资不抵债，宣告破产！其巨额持仓将被法院强制清算！"))
            # 注意：破产清算的实际抛盘/买平将在下一回合注入市场，引发次生灾害！

    # 保存本回合所有 Traces
    save_traces_to_db(conn, traces, current_turn)
```

---

## 4. LLM 接口与信息侦查机制 (The Interface)

底层的血雨腥风如何传递给玩家？我们需要给 LLM 开两个“口子”：

### 4.1 快照推送 (Snapshot Push)
在 `advance_turn` 返回的 JSON 状态快照中，**只附加 `trace_type = 'broadcast'` 的记录**。
LLM 读取这些大新闻后，会以“华尔街头版头条”的形式播报给玩家。玩家会看到哪家机构爆仓了，马斯克又发了什么疯。

### 4.2 深度调查工具 (Investigate Tool)
那些 `trace_type = 'rumor'`（传言）的动作（比如机构悄悄建仓、暗网传闻）是隐藏的。
玩家必须通过自然语言输入：“*雇个私家侦探查查到底是谁在买这只股票？*”
LLM 评估可行性后，调用新增的 MCP 工具：`investigate_abnormal_movement(stock_id)`。
MCP 提取该股票近 3 回合的 `rumor` 记录返回给 LLM。LLM 将其渲染为：“*你的线人从一家清算银行偷出了流水，原来是【文艺复兴量化】在背后狂买。*”