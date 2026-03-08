"""
市场模拟引擎 V2.0
混沌微观实体引擎：非线性滑点、机构博弈、散户情绪、蝴蝶效应
"""
from __future__ import annotations

import math
import random
import sqlite3
from typing import Any

from constants import (
    TREND_FACTOR,
    REVERT_FACTOR,
    NOISE_FACTOR,
    DECAY_FACTOR,
    SCANDAL_THRESHOLD,
    MARKET_MIN_STOCKS,
    DELISTING_CONSECUTIVE_DECLINE,
    DELISTING_SEVERE_DECLINE_TURNS,
    DELISTING_SEVERE_DECLINE_THRESHOLD,
    DELISTING_CRASH_THRESHOLD,
    DELISTING_MIN_PRICE,
    RETAIL_POWER,
    SLIPPAGE_EXPONENT,
    SENTIMENT_DECAY_RATE,
    INST_VALUE_UNDERVALUED_THRESHOLD,
    INST_VALUE_RISK_LIMIT,
    INST_SHORT_SCANDAL_THRESHOLD,
    INST_QUANT_SENTIMENT_THRESHOLD,
    INST_CAPITAL_FLOW_RATIO,
    VOLATILITY_MIN_LIQUIDITY_RATIO,
    FLOW_RATIO_CLAMP,
)


def settle_market_turn(
    conn: sqlite3.Connection,
    current_turn: int,
    player_actions: dict | None = None,
    spillover_events: list[dict] | None = None,
) -> dict:
    """
    五阶段混沌结算管线

    Args:
        conn: 游戏数据库连接
        current_turn: 当前回合数
        player_actions: 玩家交易行为 {"stock_id": net_flow_usd}
        spillover_events: 玩家闲聊蝴蝶效应事件

    Returns:
        dict: 结算结果，包含 triggered_events, market_traces, delisted_stocks
    """
    if player_actions is None:
        player_actions = {}
    if spillover_events is None:
        spillover_events = {}

    traces = []
    triggered_events = []

    # ==========================================
    # Phase 0: 宏观事件触发
    # ==========================================
    triggered_events = _trigger_macro_events(conn, current_turn)

    # ==========================================
    # Phase 1: 注意力溢出与名人发癫
    # ==========================================
    traces.extend(_process_spillovers(conn, player_actions.get("player_fame", 0), spillover_events))

    # ==========================================
    # Phase 2: 机构独立决策（基于当前情绪）
    # ==========================================
    inst_flows = _process_institutional_actors(conn, traces)

    # ==========================================
    # Phase 3-4: 流动性干涸与非线性滑点
    # 重新查询以获取最新的情绪值
    # ==========================================
    _settle_prices_nonlinear(conn, triggered_events, inst_flows, player_actions, spillover_events, player_actions.get("player_fame", 0))

    # ==========================================
    # Phase 5: 级联清算
    # ==========================================
    traces.extend(_process_liquidations(conn))

    # ==========================================
    # 保存 traces
    # ==========================================
    _save_traces(conn, traces, current_turn)

    # ==========================================
    # 退市检测
    # ==========================================
    delisted_stocks = _check_delisting(conn)

    return {
        "triggered_events": triggered_events,
        "market_traces": traces,
        "delisted_stocks": delisted_stocks,
    }


def _trigger_macro_events(conn: sqlite3.Connection, current_turn: int) -> list[dict]:
    """触发宏观事件"""
    triggered = []

    timed_events = conn.execute(
        "SELECT * FROM MacroEvents WHERE trigger_turn=? AND is_triggered=0",
        (current_turn,)
    ).fetchall()

    random_events = conn.execute(
        "SELECT * FROM MacroEvents WHERE trigger_turn=-1 AND is_triggered=0"
    ).fetchall()

    active_events = list(timed_events)
    for evt in random_events:
        if random.random() < evt["trigger_probability"]:
            active_events.append(evt)

    for evt in active_events:
        conn.execute(
            "UPDATE MacroEvents SET is_triggered=1 WHERE event_id=?",
            (evt["event_id"],)
        )
        triggered.append({
            "event_id": evt["event_id"],
            "industry_tag": evt["industry_tag"],
            "price_impact_multiplier": evt["price_impact_multiplier"],
            "description_template": evt["description_template"],
        })

    conn.commit()
    return triggered


def _process_spillovers(conn: sqlite3.Connection, player_fame: int, spillover_events: dict) -> list[dict]:
    """Phase 1: 注意力溢出与名人发癫"""
    traces = []

    for stock_id, sentiment_shift in spillover_events.items():
        impact = sentiment_shift * (player_fame / 100.0)
        conn.execute(
            "UPDATE Stock SET retail_sentiment=retail_sentiment+? WHERE id=?",
            (impact, stock_id)
        )
        traces.append({
            "stock_id": stock_id,
            "trace_type": "rumor",
            "content": "市场传言某位业界巨头私下极度看衰/看好该公司。"
        })

    celebrities = conn.execute(
        "SELECT * FROM CompanyNPC WHERE npc_type='celebrity' AND influence_power > 0"
    ).fetchall()

    all_stocks = conn.execute("SELECT id, name FROM Stock WHERE is_delisted=0").fetchall()
    if not all_stocks:
        return traces

    for celeb in celebrities:
        if random.random() < 0.05:
            target_stock = random.choice(all_stocks)
            sentiment_impact = random.uniform(-1.0, 1.0) * (celeb["influence_power"] / 100.0)
            conn.execute(
                "UPDATE Stock SET retail_sentiment=retail_sentiment+? WHERE id=?",
                (sentiment_impact, target_stock["id"])
            )
            traces.append({
                "stock_id": target_stock["id"],
                "trace_type": "broadcast",
                "content": f"突发！大V {celeb['name']} 在社交媒体上对 {target_stock['name']} 发表了极端言论！"
            })

    conn.commit()
    return traces


def _process_institutional_actors(conn: sqlite3.Connection, traces: list[dict]) -> dict[int, float]:
    """Phase 2: 机构独立决策"""
    inst_flows = {stock["id"]: 0.0 for stock in conn.execute("SELECT id FROM Stock").fetchall()}

    institutions = conn.execute("SELECT * FROM Institution WHERE status='active'").fetchall()
    all_stocks = conn.execute("SELECT * FROM Stock WHERE is_delisted=0").fetchall()

    for inst in institutions:
        for stock in all_stocks:
            flow = 0.0
            stock_id = stock["id"]

            current_stock = conn.execute("SELECT * FROM Stock WHERE id=?", (stock_id,)).fetchone()

            if inst["type"] == "value":
                flow = _value_fund_decision(conn, inst, current_stock, traces)
            elif inst["type"] == "hedge_short":
                flow = _short_fund_decision(conn, inst, current_stock, traces)
            elif inst["type"] == "quant":
                flow = _quant_fund_decision(conn, inst, current_stock)

            if flow != 0:
                inst_flows[stock_id] += flow
                _execute_inst_trade(conn, inst, stock_id, flow)

    conn.commit()
    return inst_flows


def _value_fund_decision(conn: sqlite3.Connection, inst: dict, stock: dict, traces: list[dict]) -> float:
    """价值基金决策：低估买入，止损卖出"""
    flow = 0.0
    price_gap = (stock["hidden_fundamental_value"] - stock["current_price"]) / stock["current_price"]

    if price_gap > INST_VALUE_UNDERVALUED_THRESHOLD:
        flow = inst["capital"] * INST_CAPITAL_FLOW_RATIO
        traces.append({
            "stock_id": stock["id"],
            "trace_type": "rumor",
            "content": f"{inst['name']} 似乎正在场外悄悄吸筹。"
        })

    position = conn.execute(
        "SELECT * FROM InstitutionPosition WHERE inst_id=? AND stock_id=? AND position_type='long'",
        (inst["inst_id"], stock["id"])
    ).fetchone()

    if position and position["volume_usd"] > 0 and position["avg_cost"] > 0:
        current_price = stock["current_price"]
        avg_cost = position["avg_cost"]
        
        loss_pct = (avg_cost - current_price) / avg_cost
        
        if loss_pct > INST_VALUE_RISK_LIMIT * inst["risk_tolerance"]:
            flow = -position["volume_usd"]
            traces.append({
                "stock_id": stock["id"],
                "trace_type": "broadcast",
                "content": f"惨烈！{inst['name']} 无法承受亏损，挥泪斩仓 {stock['name']}！"
            })

    return flow


def _short_fund_decision(conn: sqlite3.Connection, inst: dict, stock: dict, traces: list[dict]) -> float:
    """做空基金决策：盯紧暴雷风险"""
    flow = 0.0

    if stock["hidden_scandal_risk"] > INST_SHORT_SCANDAL_THRESHOLD:
        flow = -inst["capital"] * INST_CAPITAL_FLOW_RATIO

        if random.random() < 0.2:
            conn.execute(
                "UPDATE Stock SET retail_sentiment=retail_sentiment-0.8 WHERE id=?",
                (stock["id"],)
            )
            traces.append({
                "stock_id": stock["id"],
                "trace_type": "broadcast",
                "content": f"【做空狙击】{inst['name']} 发布长达50页报告，指控 {stock['name']} 财务造假！"
            })
        else:
            traces.append({
                "stock_id": stock["id"],
                "trace_type": "rumor",
                "content": f"暗网数据显示，有神秘对冲基金借入了海量 {stock['name']} 的股票。"
            })

    return flow


def _quant_fund_decision(conn: sqlite3.Connection, inst: dict, stock: dict) -> float:
    """量化基金决策：无脑追逐情绪"""
    flow = 0.0
    sentiment = stock["retail_sentiment"]

    if sentiment > INST_QUANT_SENTIMENT_THRESHOLD:
        flow = inst["capital"] * INST_CAPITAL_FLOW_RATIO
    elif sentiment < -INST_QUANT_SENTIMENT_THRESHOLD:
        flow = -inst["capital"] * INST_CAPITAL_FLOW_RATIO

    return flow


def _execute_inst_trade(conn: sqlite3.Connection, inst: dict, stock_id: int, flow: float):
    """执行机构交易"""
    if flow == 0:
        return

    position_type = "long" if flow > 0 else "short"
    flow_abs = abs(flow)

    position = conn.execute(
        "SELECT * FROM InstitutionPosition WHERE inst_id=? AND stock_id=? AND position_type=?",
        (inst["inst_id"], stock_id, position_type)
    ).fetchone()

    stock = conn.execute("SELECT current_price FROM Stock WHERE id=?", (stock_id,)).fetchone()
    if not stock:
        return
    price = stock["current_price"]
    quantity = flow_abs / price if price > 0 else 0

    if position:
        new_volume = position["volume_usd"] + flow_abs
        new_avg_cost = ((position["avg_cost"] * position["volume_usd"]) + flow_abs * price) / new_volume if new_volume > 0 else 0
        conn.execute(
            "UPDATE InstitutionPosition SET volume_usd=?, avg_cost=? WHERE pos_id=?",
            (new_volume, new_avg_cost, position["pos_id"])
        )
    else:
        conn.execute(
            "INSERT INTO InstitutionPosition (inst_id, stock_id, position_type, volume_usd, avg_cost) VALUES (?, ?, ?, ?, ?)",
            (inst["inst_id"], stock_id, position_type, flow_abs, price)
        )

    inst_capital = inst["capital"] - flow_abs
    conn.execute(
        "UPDATE Institution SET capital=? WHERE inst_id=?",
        (inst_capital, inst["inst_id"])
    )


def _settle_prices_nonlinear(
    conn: sqlite3.Connection,
    triggered_events: list[dict],
    inst_flows: dict[int, float],
    player_actions: dict,
    spillover_events: dict | None = None,
    player_fame: int = 0,
):
    """Phase 3-4: 流动性干涸与非线性滑点价格计算"""
    if spillover_events is None:
        spillover_events = {}

    if spillover_events:
        for stock_id, sentiment_shift in spillover_events.items():
            impact = sentiment_shift * (player_fame / 100.0)
            conn.execute(
                "UPDATE Stock SET retail_sentiment=retail_sentiment+? WHERE id=?",
                (impact, stock_id)
            )

    industry_multipliers = {}
    global_multiplier = 1.0

    for evt in triggered_events:
        if evt["industry_tag"] is None:
            global_multiplier *= evt["price_impact_multiplier"]
        else:
            tag = evt["industry_tag"]
            industry_multipliers[tag] = industry_multipliers.get(tag, 1.0) * evt["price_impact_multiplier"]

    current_turn_for_trend = conn.execute(
        "SELECT value FROM GameMeta WHERE key='current_turn'"
    ).fetchone()
    current_turn_value = int(current_turn_for_trend["value"]) if current_turn_for_trend else 1

    active_trends = conn.execute(
        """SELECT industry_tag, price_bias FROM MacroTrends
           WHERE is_active=1 AND (end_turn=-1 OR end_turn>=?)
           AND start_turn<=?""",
        (current_turn_value, current_turn_value)
    ).fetchall()

    trend_bias_map: dict = {}
    for tr in active_trends:
        key = tr["industry_tag"]
        trend_bias_map[key] = trend_bias_map.get(key, 0.0) + tr["price_bias"]

    stocks = conn.execute("SELECT * FROM Stock WHERE is_delisted=0").fetchall()

    for stock in stocks:
        sid = stock["id"]
        price = stock["current_price"]
        base_liq = stock["base_liquidity"]
        sentiment = stock["retail_sentiment"]
        scandal_risk = stock["hidden_scandal_risk"]

        retail_flow = sentiment * base_liq * RETAIL_POWER

        player_flow = player_actions.get(sid, 0.0)

        total_net_flow = retail_flow + inst_flows.get(sid, 0.0) + player_flow

        volatility = min(1.0, scandal_risk / 100.0 + abs(sentiment) * 0.5)
        current_liquidity = max(base_liq * VOLATILITY_MIN_LIQUIDITY_RATIO,
                               base_liq * (1.0 - volatility * 0.8))

        flow_ratio = abs(total_net_flow) / current_liquidity
        flow_ratio = min(flow_ratio, FLOW_RATIO_CLAMP)

        price_impact_pct = math.copysign(math.pow(flow_ratio, SLIPPAGE_EXPONENT), total_net_flow)

        industry = stock["industry_tag"]
        macro_multiplier = global_multiplier
        if industry in industry_multipliers:
            macro_multiplier *= industry_multipliers[industry]

        revert_delta = (stock["hidden_fundamental_value"] - price) / price * REVERT_FACTOR
        new_price = max(0.01, round(price * (1.0 + price_impact_pct + revert_delta) * macro_multiplier, 2))

        new_momentum = stock["hidden_momentum"] * DECAY_FACTOR
        trend_bias = trend_bias_map.get(None, 0.0) + trend_bias_map.get(industry, 0.0)
        new_momentum += trend_bias
        new_momentum = max(-10.0, min(10.0, new_momentum))

        if scandal_risk >= SCANDAL_THRESHOLD:
            new_price = round(new_price * 0.4, 2)
            new_scandal_risk = max(0, scandal_risk - 20)
        else:
            new_scandal_risk = scandal_risk

        new_sentiment = sentiment * SENTIMENT_DECAY_RATE

        price_change_rate = (new_price - price) / price if price > 0 else 0
        new_consecutive_decline = stock["consecutive_decline_turns"] + 1 if price_change_rate < 0 else 0

        conn.execute(
            """UPDATE Stock SET
               current_price=?, hidden_momentum=?, hidden_scandal_risk=?,
               consecutive_decline_turns=?, last_turn_price=?,
               current_liquidity=?, retail_sentiment=?, volatility_index=?
               WHERE id=?""",
            (new_price, new_momentum, new_scandal_risk,
             new_consecutive_decline, price, current_liquidity, new_sentiment, volatility, sid)
        )

    conn.commit()


def _process_liquidations(conn: sqlite3.Connection) -> list[dict]:
    """Phase 5: 级联清算与机构破产"""
    traces = []

    institutions = conn.execute("SELECT * FROM Institution WHERE status='active'").fetchall()

    for inst in institutions:
        total_assets = 0.0

        positions = conn.execute(
            "SELECT * FROM InstitutionPosition WHERE inst_id=?",
            (inst["inst_id"],)
        ).fetchall()

        for pos in positions:
            stock = conn.execute("SELECT current_price FROM Stock WHERE id=?", (pos["stock_id"],)).fetchone()
            if stock:
                if pos["position_type"] == "long":
                    total_assets += pos["volume_usd"] / pos["avg_cost"] * stock["current_price"] if pos["avg_cost"] > 0 else 0
                else:
                    avg_cost = pos["avg_cost"]
                    current_value = pos["volume_usd"] / avg_cost * stock["current_price"] if avg_cost > 0 else 0
                    total_assets += pos["volume_usd"] - (pos["volume_usd"] / avg_cost * stock["current_price"] - pos["volume_usd"]) if avg_cost > 0 else 0

        net_worth = inst["capital"] + total_assets

        if net_worth < 0:
            conn.execute(
                "UPDATE Institution SET status='bankrupt' WHERE inst_id=?",
                (inst["inst_id"],)
            )
            traces.append({
                "stock_id": None,
                "trace_type": "broadcast",
                "content": f"【金融核弹】顶级机构 {inst['name']} 资不抵债，宣告破产！其巨额持仓将被法院强制清算！"
            })

            conn.execute("DELETE FROM InstitutionPosition WHERE inst_id=?", (inst["inst_id"],))

    conn.commit()
    return traces


def _save_traces(conn: sqlite3.Connection, traces: list[dict], turn: int):
    """保存市场痕迹到数据库"""
    for trace in traces:
        conn.execute(
            "INSERT INTO MarketTrace (turn, stock_id, trace_type, content) VALUES (?, ?, ?, ?)",
            (turn, trace.get("stock_id"), trace["trace_type"], trace["content"])
        )
    conn.commit()


def _check_delisting(conn: sqlite3.Connection) -> list[dict]:
    """检测退市条件"""
    total_stocks = conn.execute(
        "SELECT COUNT(*) as count FROM Stock WHERE is_delisted=0"
    ).fetchone()["count"]

    if total_stocks <= MARKET_MIN_STOCKS:
        return []

    delisted_stocks = []
    stocks = conn.execute(
        """SELECT id, name, current_price, last_turn_price,
                  consecutive_decline_turns, industry_tag
           FROM Stock WHERE is_delisted=0"""
    ).fetchall()

    for stock in stocks:
        stock_id = stock["id"]
        price = stock["current_price"]
        last_price = stock["last_turn_price"]
        consecutive_decline = stock["consecutive_decline_turns"]

        delisting_reason = None

        if price < DELISTING_MIN_PRICE:
            delisting_reason = f"股价跌破{DELISTING_MIN_PRICE}元面值"
        elif last_price > 0:
            decline_rate = (last_price - price) / last_price
            if decline_rate >= DELISTING_CRASH_THRESHOLD:
                delisting_reason = f"单日暴跌{decline_rate*100:.1f}%"
        elif consecutive_decline >= DELISTING_SEVERE_DECLINE_TURNS:
            delisting_reason = f"连续{DELISTING_SEVERE_DECLINE_TURNS}回合暴跌"
        elif consecutive_decline >= DELISTING_CONSECUTIVE_DECLINE:
            delisting_reason = f"连续{consecutive_decline}回合下跌"

        if delisting_reason:
            conn.execute("UPDATE Stock SET is_delisted=1 WHERE id=?", (stock_id,))
            delisted_stocks.append({
                "id": stock_id,
                "name": stock["name"],
                "reason": delisting_reason,
                "final_price": price,
                "industry_tag": stock["industry_tag"],
            })

    conn.commit()
    return delisted_stocks


def calculate_trade_impact(conn: sqlite3.Connection, stock_id: int, trade_volume: float) -> float:
    """
    计算交易对价格的冲击（兼容旧接口）
    """
    stock = conn.execute(
        "SELECT current_liquidity FROM Stock WHERE id=?",
        (stock_id,)
    ).fetchone()

    if not stock:
        return 0.0

    liquidity = stock["current_liquidity"]
    impact = trade_volume / liquidity
    return impact


def add_scandal_risk(conn: sqlite3.Connection, stock_id: int, delta: int):
    """
    增加股票的暴雷风险
    """
    conn.execute(
        "UPDATE Stock SET hidden_scandal_risk=hidden_scandal_risk+? WHERE id=?",
        (delta, stock_id)
    )
    conn.commit()


def liquidate_delisted_holdings(conn: sqlite3.Connection, stock_id: int, final_price: float) -> dict:
    """
    强制清算玩家持有的退市股票
    """
    holding = conn.execute(
        "SELECT quantity, avg_cost FROM Portfolio WHERE player_id=1 AND stock_id=? AND quantity>0",
        (stock_id,)
    ).fetchone()

    if not holding:
        return {"quantity": 0, "cash_received": 0.0}

    quantity = holding["quantity"]
    cash_received = quantity * final_price

    conn.execute(
        "UPDATE Portfolio SET quantity=0 WHERE player_id=1 AND stock_id=?",
        (stock_id,)
    )

    conn.execute(
        "UPDATE Player SET cash=cash+? WHERE id=1",
        (cash_received,)
    )

    conn.commit()

    return {
        "quantity": quantity,
        "cash_received": round(cash_received, 2),
        "avg_cost": holding["avg_cost"],
        "loss": round((holding["avg_cost"] - final_price) * quantity, 2),
    }
