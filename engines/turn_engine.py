"""
回合推进引擎
负责构建状态快照、推进回合主流程
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from db import game_db
from engines import market_engine, state_engine, intent_engine
from engines import event_engine, ending_engine, ipo_engine
from constants import SNAPSHOT_TOP_MOVER_COUNT


def build_snapshot(conn: sqlite3.Connection, triggered_events: list[dict]) -> dict:
    """
    构建发送给 LLM 的状态快照
    
    使用智能过滤减少 Token 消耗：
    - 只推送持仓股票、异动股票、情报关联股票、宏观事件相关股票
    
    Args:
        conn: 游戏数据库连接
        triggered_events: 本回合触发的宏观事件列表
    
    Returns:
        dict: 完整的状态快照
    """
    # ── 获取元数据 ──────────────────────────────────────────
    meta_rows = conn.execute("SELECT key, value FROM GameMeta").fetchall()
    meta = {row["key"]: row["value"] for row in meta_rows}
    
    current_turn = int(meta.get("current_turn", 0))
    week = current_turn
    month = (current_turn - 1) // 4 + 1 if current_turn > 0 else 1
    quarter = (month - 1) // 3 + 1
    
    # ── 玩家信息 ──────────────────────────────────────────
    player = conn.execute("SELECT * FROM Player WHERE id=1").fetchone()
    
    if not player:
        return {"error": "NO_PLAYER"}
    
    # 构建职位名称
    job_name = None
    if player["current_job_company_id"]:
        stock = conn.execute(
            "SELECT name FROM Stock WHERE id=?",
            (player["current_job_company_id"],)
        ).fetchone()
        if stock:
            job_name = f"Level-{player['job_level']} @ {stock['name']}"
    
    player_dict = {
        "cash": player["cash"],
        "fame": player["fame"],
        "followers": player["followers"],
        "social_reach": player["social_reach"],
        "audience_tags": json.loads(player["audience_tags"]),
        "sec_heat": player["sec_heat"],
        "jail_turns_left": player["jail_turns_left"],
        "in_bankruptcy": bool(player["in_bankruptcy"]),
        "job": job_name,
        "job_level": player["job_level"],
        "delusion_level": player["delusion_level"],
    }
    
    # ── 活跃 Buff 摘要（不含 data 字段）──────────────────
    buffs_raw = conn.execute(
        """SELECT buff_type, related_entity_id, duration_turns 
           FROM PlayerBuffs WHERE duration_turns != 0"""
    ).fetchall()
    
    active_buffs = []
    for b in buffs_raw:
        entity_name = _get_entity_name(conn, b["related_entity_id"])
        active_buffs.append({
            "buff_type": b["buff_type"],
            "target_name": entity_name,
            "turns_left": b["duration_turns"],
        })
    
    # ── 智能市场快照 ───────────────────────────────────────
    all_stocks = conn.execute(
        "SELECT id, name, current_price, industry_tag FROM Stock"
    ).fetchall()
    
    # 1. 持仓股票
    holding_ids = set(
        row["stock_id"] for row in
        conn.execute(
            "SELECT stock_id FROM Portfolio WHERE player_id=1 AND quantity>0"
        ).fetchall()
    )
    
    # 2. Buff 关联股票
    buff_stock_ids = set(
        b["related_entity_id"] for b in buffs_raw
        if b["buff_type"] in ("company_financials", "macro_event_intel")
        and b["related_entity_id"]
    )
    
    # 3. 宏观事件涉及的行业股票
    event_industries = {
        e["industry_tag"] for e in triggered_events 
        if e.get("industry_tag")
    }
    event_stock_ids = set(
        s["id"] for s in all_stocks 
        if s["industry_tag"] in event_industries
    )
    
    # 4. Top Mover（涨跌幅最大的股票）
    # 读取上一回合价格
    prev_prices_str = meta.get("prev_prices", "{}")
    prev_prices = json.loads(prev_prices_str) if prev_prices_str else {}
    
    movers = sorted(
        all_stocks,
        key=lambda s: abs(
            s["current_price"] - prev_prices.get(str(s["id"]), s["current_price"])
        ),
        reverse=True
    )[:SNAPSHOT_TOP_MOVER_COUNT]
    top_mover_ids = {s["id"] for s in movers}
    
    # 合并需要推送的股票集合
    snapshot_ids = holding_ids | top_mover_ids | buff_stock_ids | event_stock_ids
    
    # 构建市场快照
    market_snapshot = []
    for s in all_stocks:
        if s["id"] not in snapshot_ids:
            continue
        
        prev_price = prev_prices.get(str(s["id"]), s["current_price"])
        
        # 确定推送原因
        if s["id"] in holding_ids:
            reason = "holding"
        elif s["id"] in top_mover_ids:
            reason = "top_mover"
        elif s["id"] in buff_stock_ids:
            reason = "buff_related"
        else:
            reason = "macro_event"
        
        market_snapshot.append({
            "id": s["id"],
            "name": s["name"],
            "price": s["current_price"],
            "price_change": round(s["current_price"] - prev_price, 2),
            "reason": reason,
        })
    
    # ── 更新 prev_prices ─────────────────────────────────
    new_prev = {str(s["id"]): s["current_price"] for s in all_stocks}
    conn.execute(
        "INSERT OR REPLACE INTO GameMeta VALUES ('prev_prices', ?)",
        (json.dumps(new_prev),)
    )
    conn.commit()
    
    # ── 活跃宏观趋势（叙事一致性锚点）──────────────────────────
    # 只推送 name + description + industry_tag，隐藏 price_bias
    trend_rows = conn.execute(
        """SELECT name, description, industry_tag, direction
           FROM MacroTrends
           WHERE is_active=1 AND (end_turn=-1 OR end_turn>=?)
           AND start_turn<=?
           ORDER BY trend_id""",
        (current_turn, current_turn)
    ).fetchall()

    active_trends = [
        {
            "name": tr["name"],
            "description": tr["description"],
            "industry_tag": tr["industry_tag"],
            "direction": tr["direction"],
        }
        for tr in trend_rows
    ]

    # ── 玩家背包（语义化资产）────────────────────────────────
    inventory_rows = conn.execute(
        "SELECT item_id, name, category_tag, description, estimated_value, status, acquire_turn FROM PlayerInventory"
    ).fetchall()
    inventory_list = [dict(row) for row in inventory_rows]

    # ── 玩家债务──────────────────────────────────────────────
    debt_rows = conn.execute(
        "SELECT debt_id, debt_type, amount_owed, collateral_item_id, due_turn, target_stock_id FROM PlayerDebts"
    ).fetchall()
    debt_list = [dict(row) for row in debt_rows]

    # ── 组装完整快照 ─────────────────────────────────────
    # 获取本回合的 broadcast traces（供 LLM 播报）
    broadcast_traces = conn.execute(
        "SELECT * FROM MarketTrace WHERE turn=? AND trace_type='broadcast' ORDER BY trace_id",
        (current_turn,)
    ).fetchall()

    market_news = [
        {"content": t["content"], "stock_id": t["stock_id"]}
        for t in broadcast_traces
    ]

    return {
        "turn": current_turn,
        "calendar": {
            "week": week,
            "month": month,
            "quarter": quarter
        },
        "triggered_events": triggered_events,
        "active_trends": active_trends,
        "player": player_dict,
        "active_buffs": active_buffs,
        "inventory": inventory_list,
        "debts": debt_list,
        "market_snapshot": market_snapshot,
        "market_news": market_news,
    }


def _get_entity_name(conn: sqlite3.Connection, entity_id: int | None) -> str | None:
    """
    获取实体名称（股票或NPC）
    
    Args:
        conn: 数据库连接
        entity_id: 实体ID
    
    Returns:
        str | None: 实体名称
    """
    if not entity_id:
        return None
    
    # 尝试从 Stock 表查找
    stock = conn.execute(
        "SELECT name FROM Stock WHERE id=?", (entity_id,)
    ).fetchone()
    
    if stock:
        return stock["name"]
    
    # 尝试从 CompanyNPC 表查找
    npc = conn.execute(
        "SELECT name FROM CompanyNPC WHERE npc_id=?", (entity_id,)
    ).fetchone()
    
    if npc:
        return npc["name"]
    
    return None


def advance_turn(conn: sqlite3.Connection, story_log: str = "", intents: list[dict] = None) -> dict:
    """
    推进回合（核心主流程）
    
    改造后流程：
    0. 保存上回合剧情日志到 ActionLog（推进前）
    1. 处理玩家意图数组（scheme/trade/work），结果暂存
    2. 回合数+1，计算日历
    3. 市场结算（价格+事件）+ 轮询 ScheduledEvents 延时事件
    4. 月末发放薪资
    5. 自动上班
    6. 监管热度检查
    7. 妄想度区间检查（M3）
    8. 减少坐牢时间
    9. Buff 倒计时
    10. 检查破产状态
    11. 晋升检查（M3）
    12. 结局检查（M3）
    13. 构建并返回状态快照（追加 intent_results 字段）
    
    Args:
        conn: 游戏数据库连接
        story_log: 上回合剧情摘要（100字以内），首回合填"游戏开始"
        intents: 玩家意图数组，无操作传 []
    
    Returns:
        dict: 完整的状态快照 + intent_results
    """
    if intents is None:
        intents = []
    
    # 0. 保存上回合剧情日志（推进前，记录到当前 turn）
    meta = conn.execute("SELECT value FROM GameMeta WHERE key='current_turn'").fetchone()
    current_turn_before = int(meta["value"]) if meta else 0
    
    if story_log:
        conn.execute(
            "INSERT INTO ActionLog (turn, summary) VALUES (?, ?)",
            (current_turn_before, story_log)
        )
        conn.commit()
    
    # 1. 处理玩家意图数组（在回合推进前执行，允许立即生效的操作）
    # 并收集玩家交易行为用于市场引擎
    intent_results = []
    interrupted = False
    interrupt_reason = None
    player_trade_actions = {}
    spillover_events = {}

    for idx, intent in enumerate(intents):
        ap_type = intent.get("ap_type")

        if ap_type == "scheme_ap":
            # 检查是否是 spillover_ap
            if intent.get("intent_type") == "spillover":
                result = _process_spillover_intent(conn, intent)
                spillover_events.update(result.get("spillover_data", {}))
            else:
                result = intent_engine._process_scheme_intent(conn, intent)
        elif ap_type == "trade_ap":
            # trade_ap 直接调用交易工具（内部执行）
            result = _process_trade_intent_internal(conn, intent)
            # 收集交易行为用于市场冲击计算
            _collect_trade_action(intent, player_trade_actions)
        elif ap_type == "work_ap":
            result = intent_engine._process_work_intent(conn, intent)
        else:
            result = {
                "outcome": "rejected",
                "reject_reason": "INVALID_AP_TYPE",
                "state_changes": {},
                "narrative_hint": f"未知的 AP 类型: {ap_type}"
            }

        result["index"] = idx
        result["ap_type"] = ap_type
        intent_results.append(result)

        if result.get("interrupt"):
            interrupted = True
            interrupt_reason = result.get("interrupt_reason")
            break

    # 2. 回合数+1
    current_turn = game_db.increment_turn(conn)

    # 3. V2.0 市场结算（五阶段管线）
    player = conn.execute("SELECT fame from Player WHERE id=1").fetchone()
    player_fame = player["fame"] if player else 0

    market_result = market_engine.settle_market_turn(
        conn,
        current_turn,
        player_actions={"player_fame": player_fame, **player_trade_actions},
        spillover_events=spillover_events
    )

    triggered_events = market_result.get("triggered_events", [])
    market_traces = market_result.get("market_traces", [])
    delisted_stocks = market_result.get("delisted_stocks", [])

    delisting_liquidations = []
    for delisted in delisted_stocks:
        liquidation = market_engine.liquidate_delisted_holdings(
            conn, delisted["id"], delisted["final_price"]
        )
        if liquidation["quantity"] > 0:
            delisting_liquidations.append({
                "stock_name": delisted["name"],
                "reason": delisted["reason"],
                **liquidation
            })
    
    # 5. IPO 检测（退市后检测，保持大盘平衡）
    ipo_result = ipo_engine.trigger_ipo(conn, current_turn)
    
    # 6. 延时事件处理（M3）
    scheduled_events = event_engine.tick_scheduled_events(conn, current_turn)
    triggered_events.extend(scheduled_events)
    
    # 4. 月末发放薪资
    if current_turn % 4 == 0:
        salary_result = state_engine.pay_salary(conn)
        
        # M3: 破产状态下的底层打工薪资
        player = conn.execute(
            "SELECT in_bankruptcy, jail_turns_left FROM Player WHERE id=1"
        ).fetchone()
        
        if player and player["in_bankruptcy"] and player["jail_turns_left"] == 0:
            state_engine.bankruptcy_job(conn)
    
    # 5. 自动上班
    state_engine.auto_work(conn)
    
    # 6. 监管热度检查
    sec_result = state_engine.check_sec_heat(conn)
    
    # M3: 如果触发逮捕，初始化监狱NPC
    if "ARRESTED" in sec_result.get("triggered_events", []):
        _init_prison_if_needed(conn)
    
    # 7. 妄想度区间检查（M3）
    delusion_result = state_engine.check_delusion_tier(conn)
    
    # 8. 减少坐牢时间
    state_engine.decrement_jail_time(conn)
    
    # 9. Buff 倒计时
    state_engine.tick_buffs(conn)
    
    # 10. 检查破产状态
    state_engine.check_bankruptcy(conn)
    
    # 11. 晋升检查（M3）
    player = conn.execute(
        "SELECT job_performance FROM Player WHERE id=1"
    ).fetchone()
    
    if player and player["job_performance"] > 0:
        # 检查是否满足晋升条件
        from constants import JOB_LEVEL_THRESHOLD
        if player["job_performance"] >= JOB_LEVEL_THRESHOLD:
            state_engine.check_promotion(conn)
    
    # 12. 结局检查（M3）
    ending_result = ending_engine.check_endings(conn)
    
    # 13. 构建状态快照
    snapshot = build_snapshot(conn, triggered_events)
    
    # M3: 将结局信息添加到快照
    if ending_result.get("triggered"):
        snapshot["ending"] = ending_result
    
    # M3: 将妄想度信息添加到快照
    if delusion_result:
        snapshot["delusion_info"] = {
            "tier": delusion_result.get("tier"),
            "level": delusion_result.get("level"),
            "effects": delusion_result.get("effects", {}).get("description"),
        }
    
    # 追加意图处理结果
    snapshot["intent_results"] = intent_results
    snapshot["interrupted"] = interrupted
    if interrupt_reason:
        snapshot["interrupt_reason"] = interrupt_reason
    
    # 追加退市信息
    if delisted_stocks:
        snapshot["delisted_stocks"] = delisted_stocks
    if delisting_liquidations:
        snapshot["delisting_liquidations"] = delisting_liquidations
    
    # 追加 IPO 信息
    if ipo_result:
        snapshot["ipo"] = ipo_result

    # V2.0: 添加市场痕迹
    snapshot["market_traces"] = market_traces

    return snapshot


def _process_trade_intent_internal(conn: sqlite3.Connection, intent: dict) -> dict:
    """
    内部处理交易意图（trade_ap）
    
    直接调用 buy_stock / sell_stock 逻辑，不走独立工具
    
    Args:
        conn: 游戏数据库连接
        intent: 交易意图，包含 stock_id, quantity, action ("buy"/"sell")
    
    Returns:
        dict: 检定结果
    """
    from tools import trade_tools
    
    action = intent.get("action", "buy")
    stock_id = intent.get("stock_id")
    quantity = intent.get("quantity", 0)
    
    if not stock_id or quantity <= 0:
        return {
            "outcome": "rejected",
            "reject_reason": "INVALID_PARAM",
            "state_changes": {},
            "narrative_hint": "交易参数无效"
        }
    
    try:
        if action == "buy":
            result_json = trade_tools.tool_buy_stock(conn, stock_id, quantity)
        elif action == "sell":
            result_json = trade_tools.tool_sell_stock(conn, stock_id, quantity)
        else:
            return {
                "outcome": "rejected",
                "reject_reason": "INVALID_ACTION",
                "state_changes": {},
                "narrative_hint": f"未知交易类型: {action}"
            }
        
        result = json.loads(result_json)
        
        if "error" in result:
            return {
                "outcome": "rejected",
                "reject_reason": result["error"],
                "state_changes": {},
                "narrative_hint": result.get("message", "交易失败")
            }
        
        return {
            "outcome": "success",
            "reject_reason": None,
            "state_changes": result,
            "narrative_hint": f"交易已执行：{action} {quantity}股"
        }
    
    except Exception as e:
        return {
            "outcome": "rejected",
            "reject_reason": "TRADE_FAILED",
            "state_changes": {},
            "narrative_hint": str(e)
        }


def _init_prison_if_needed(conn: sqlite3.Connection):
    """
    如果玩家首次进入监狱，初始化监狱专属NPC

    Args:
        conn: 游戏数据库连接
    """
    prison_npc_count = conn.execute(
        "SELECT COUNT(*) as count FROM CompanyNPC WHERE company_id IS NULL"
    ).fetchone()["count"]

    if prison_npc_count == 0:
        state_engine.init_prison_npcs(conn)


def _collect_trade_action(intent: dict, actions: dict):
    """
    收集玩家交易行为用于市场冲击计算

    Args:
        intent: 交易意图
        actions: 存储交易行为的字典
    """
    stock_id = intent.get("stock_id")
    if not stock_id:
        return

    action = intent.get("action")
    quantity = intent.get("quantity", 0)

    from tools import trade_tools
    stock = trade_tools._get_stock_price(None, stock_id)
    if not stock:
        return

    price = stock["current_price"]
    trade_value = quantity * price

    if action == "buy":
        actions[stock_id] = actions.get(stock_id, 0) + trade_value
    elif action == "sell":
        actions[stock_id] = actions.get(stock_id, 0) - trade_value


def _process_spillover_intent(conn: sqlite3.Connection, intent: dict) -> dict:
    """
    处理蝴蝶效应意图

    Args:
        conn: 数据库连接
        intent: spillover_ap 意图

    Returns:
        dict: 处理结果，包含 spillover_data
    """
    stock_id = intent.get("target_stock_id")
    sentiment_shift = intent.get("sentiment_shift", 0.0)

    if not stock_id:
        return {
            "outcome": "rejected",
            "reject_reason": "INVALID_PARAM",
            "spillover_data": {},
            "narrative_hint": "蝴蝶效应需要指定目标股票"
        }

    return {
        "outcome": "success",
        "spillover_data": {stock_id: sentiment_shift},
        "narrative_hint": f"你的言论将对 {stock_id} 产生市场影响"
    }

