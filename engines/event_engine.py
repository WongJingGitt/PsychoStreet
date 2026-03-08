"""
延时事件引擎
负责处理ScheduledEvents表中的延时事件倒计时、触发与消息泄露
"""

import json
import random
import sqlite3
from typing import Any

from constants import (
    EVENT_LEAK_PROBABILITY,
    EVENT_TYPE_DURATION,
    UNDERGROUND_LOAN_INTEREST,
)


def tick_scheduled_events(conn: sqlite3.Connection, current_turn: int) -> list[dict]:
    """
    处理延时事件倒计时与触发
    
    每回合调用一次，执行以下操作：
    1. 将所有 pending 事件的 turns_remaining 减 1
    2. 检查消息泄露（小概率将 status 改为 leaked）
    3. 触发到期事件（turns_remaining = 0），读取 context 执行结算
    4. 将触发的事件标记为 triggered
    
    Args:
        conn: 游戏数据库连接
        current_turn: 当前回合数
    
    Returns:
        list[dict]: 本回合触发的事件列表，每项包含：
            - event_id: 事件ID
            - event_type: 事件类型
            - outcome: "success" | "failure" | "leaked"
            - narrative: 叙事文本
            - state_changes: 状态变更摘要
    """
    triggered_events = []
    
    # ── 步骤1: 倒计时 ───────────────────────────────────────
    conn.execute(
        """UPDATE ScheduledEvents 
           SET turns_remaining=turns_remaining-1 
           WHERE status='pending' AND turns_remaining > 0"""
    )
    
    # ── 步骤2: 检查消息泄露 ─────────────────────────────────
    pending_events = conn.execute(
        """SELECT event_id, event_type, target_id, context 
           FROM ScheduledEvents WHERE status='pending'"""
    ).fetchall()
    
    for evt in pending_events:
        if random.random() < EVENT_LEAK_PROBABILITY:
            # 消息泄露
            conn.execute(
                "UPDATE ScheduledEvents SET status='leaked' WHERE event_id=?",
                (evt["event_id"],)
            )
            
            # 泄露事件也添加到触发列表
            triggered_events.append({
                "event_id": evt["event_id"],
                "event_type": evt["event_type"],
                "outcome": "leaked",
                "narrative": "你的计划意外泄露，相关方已经有所警觉。",
                "state_changes": {"sec_heat_delta": 10},
            })
            
            # 增加监管热度
            conn.execute(
                "UPDATE Player SET sec_heat=MIN(100, sec_heat+10) WHERE id=1"
            )
    
    # ── 步骤3: 触发到期事件 ─────────────────────────────────
    due_events = conn.execute(
        """SELECT event_id, event_type, target_id, context 
           FROM ScheduledEvents 
           WHERE status='pending' AND turns_remaining <= 0"""
    ).fetchall()
    
    for evt in due_events:
        result = _execute_scheduled_event(conn, evt, current_turn)
        triggered_events.append(result)
        
        # 标记为已触发
        conn.execute(
            "UPDATE ScheduledEvents SET status='triggered' WHERE event_id=?",
            (evt["event_id"],)
        )
    
    conn.commit()
    return triggered_events


def _execute_scheduled_event(
    conn: sqlite3.Connection,
    event: dict,
    current_turn: int
) -> dict:
    """
    执行单个延时事件的最终结算
    
    Args:
        conn: 游戏数据库连接
        event: 事件字典（包含event_id, event_type, target_id, context）
        current_turn: 当前回合数
    
    Returns:
        dict: 事件执行结果
    """
    event_id = event["event_id"]
    event_type = event["event_type"]
    target_id = event["target_id"]
    
    try:
        context = json.loads(event["context"]) if event["context"] else {}
    except json.JSONDecodeError:
        context = {}
    
    # 根据事件类型分发处理
    if event_type == "hire_investigator":
        return _handle_hire_investigator(conn, event_id, target_id, context)
    elif event_type == "bribe_npc":
        return _handle_bribe_npc(conn, event_id, target_id, context)
    elif event_type == "arrange_meeting":
        return _handle_arrange_meeting(conn, event_id, target_id, context)
    elif event_type == "major_scheme":
        return _handle_major_scheme(conn, event_id, target_id, context)
    elif event_type == "underground_loan":
        return _handle_underground_loan(conn, event_id, target_id, context, current_turn)
    elif event_type == "sec_inquiry":
        return _handle_sec_inquiry(conn, event_id, target_id, context)
    elif event_type == "debt_collection":
        return _handle_debt_collection(conn, event_id, target_id, context)
    elif event_type == "scheme_market_impact":
        return _handle_scheme_market_impact(conn, event_id, target_id, context)
    else:
        return {
            "event_id": event_id,
            "event_type": event_type,
            "outcome": "failure",
            "narrative": f"未知的事件类型：{event_type}",
            "state_changes": {},
        }


def _handle_hire_investigator(
    conn: sqlite3.Connection,
    event_id: int,
    target_id: int,
    context: dict
) -> dict:
    """
    处理雇私家侦探事件
    
    Args:
        conn: 数据库连接
        event_id: 事件ID
        target_id: 目标NPC ID
        context: 上下文（包含侦探能力、目标信息等）
    
    Returns:
        dict: 事件结果
    """
    # 掷骰子检定
    success_rate = context.get("success_rate", 0.7)
    success = random.random() < success_rate
    
    if success:
        # 成功获取NPC情报
        if target_id:
            # 获取NPC的hidden_traits
            npc = conn.execute(
                "SELECT hidden_traits FROM CompanyNPC WHERE npc_id=?",
                (target_id,)
            ).fetchone()
            
            if npc:
                # 创建情报Buff
                conn.execute(
                    """INSERT INTO PlayerBuffs 
                       (player_id, buff_type, related_entity_id, data, duration_turns)
                       VALUES (1, 'npc_weakness', ?, ?, -1)""",
                    (target_id, npc["hidden_traits"])
                )
        
        return {
            "event_id": event_id,
            "event_type": "hire_investigator",
            "outcome": "success",
            "narrative": "私家侦探成功获取了目标的情报，你掌握了对方的弱点。",
            "state_changes": {"buff_added": "npc_weakness"},
        }
    else:
        return {
            "event_id": event_id,
            "event_type": "hire_investigator",
            "outcome": "failure",
            "narrative": "私家侦探调查失败，没有发现有价值的信息。",
            "state_changes": {},
        }


def _handle_bribe_npc(
    conn: sqlite3.Connection,
    event_id: int,
    target_id: int,
    context: dict
) -> dict:
    """
    处理贿赂NPC事件（延时版）
    
    Args:
        conn: 数据库连接
        event_id: 事件ID
        target_id: 目标NPC ID
        context: 上下文（包含贿赂金额、方式等）
    
    Returns:
        dict: 事件结果
    """
    if not target_id:
        return {
            "event_id": event_id,
            "event_type": "bribe_npc",
            "outcome": "failure",
            "narrative": "贿赂目标不存在。",
            "state_changes": {},
        }
    
    # 更新NPC关系
    conn.execute(
        """UPDATE CompanyNPC 
           SET relationship_with_player=relationship_with_player+10 
           WHERE npc_id=?""",
        (target_id,)
    )
    
    return {
        "event_id": event_id,
        "event_type": "bribe_npc",
        "outcome": "success",
        "narrative": "经过一番周折，你成功收买了目标。",
        "state_changes": {"relationship_delta": 10},
    }


def _handle_arrange_meeting(
    conn: sqlite3.Connection,
    event_id: int,
    target_id: int,
    context: dict
) -> dict:
    """
    处理安排会面事件
    
    Args:
        conn: 数据库连接
        event_id: 事件ID
        target_id: 目标NPC ID
        context: 上下文（包含会面目的、方式等）
    
    Returns:
        dict: 事件结果
    """
    if not target_id:
        return {
            "event_id": event_id,
            "event_type": "arrange_meeting",
            "outcome": "failure",
            "narrative": "会面对象不存在。",
            "state_changes": {},
        }
    
    npc = conn.execute(
        "SELECT name, role FROM CompanyNPC WHERE npc_id=?",
        (target_id,)
    ).fetchone()
    
    if not npc:
        return {
            "event_id": event_id,
            "event_type": "arrange_meeting",
            "outcome": "failure",
            "narrative": "会面对象不存在。",
            "state_changes": {},
        }
    
    # 创建会面Buff
    conn.execute(
        """INSERT INTO PlayerBuffs 
           (player_id, buff_type, related_entity_id, data, duration_turns)
           VALUES (1, 'meeting_arranged', ?, ?, 2)""",
        (target_id, json.dumps({"purpose": context.get("purpose", "商务会面")}))
    )
    
    return {
        "event_id": event_id,
        "event_type": "arrange_meeting",
        "outcome": "success",
        "narrative": f"你成功安排了与 {npc['name']}（{npc['role']}）的会面。",
        "state_changes": {"buff_added": "meeting_arranged"},
    }


def _handle_major_scheme(
    conn: sqlite3.Connection,
    event_id: int,
    target_id: int,
    context: dict
) -> dict:
    """
    处理重大策划事件
    
    Args:
        conn: 数据库连接
        event_id: 事件ID
        target_id: 目标Stock/NPC ID
        context: 上下文（包含策划详情、影响范围等）
    
    Returns:
        dict: 事件结果
    """
    # 复杂的策划事件，基于context中的检定参数
    success_rate = context.get("success_rate", 0.6)
    success = random.random() < success_rate
    
    if success:
        # 成功执行策划，可能影响股价、NPC等
        impact_type = context.get("impact_type", "market")
        
        if impact_type == "market" and target_id:
            # 市场影响：推高/打压股价
            price_impact = context.get("price_impact", 0.1)
            conn.execute(
                """UPDATE Stock 
                   SET current_price=current_price * ?,
                       hidden_momentum=hidden_momentum + ?
                   WHERE id=?""",
                (1 + price_impact, price_impact * 10, target_id)
            )
        
        return {
            "event_id": event_id,
            "event_type": "major_scheme",
            "outcome": "success",
            "narrative": "你的重大策划顺利执行，产生了预期的影响。",
            "state_changes": context.get("state_changes", {}),
        }
    else:
        # 失败：增加监管热度
        heat_delta = context.get("illegality_score", 5) * 2
        conn.execute(
            "UPDATE Player SET sec_heat=MIN(100, sec_heat+?) WHERE id=1",
            (heat_delta,)
        )
        
        return {
            "event_id": event_id,
            "event_type": "major_scheme",
            "outcome": "failure",
            "narrative": "策划失败了，引起了监管机构的注意。",
            "state_changes": {"sec_heat_delta": heat_delta},
        }


def _handle_underground_loan(
    conn: sqlite3.Connection,
    event_id: int,
    target_id: int,
    context: dict,
    current_turn: int
) -> dict:
    """
    处理地下钱庄借贷事件
    
    Args:
        conn: 数据库连接
        event_id: 事件ID
        target_id: 债权人ID（通常为None）
        context: 上下文（包含借款金额、利息等）
        current_turn: 当前回合
    
    Returns:
        dict: 事件结果
    """
    amount = context.get("amount", 0)
    interest = UNDERGROUND_LOAN_INTEREST
    repayment = amount * (1 + interest)
    deadline = current_turn + 5  # 5回合后还款
    
    # 增加现金
    conn.execute(
        "UPDATE Player SET cash=cash+? WHERE id=1",
        (amount,)
    )
    
    # 创建还款倒计时事件
    conn.execute(
        """INSERT INTO ScheduledEvents 
           (player_id, event_type, target_id, turns_remaining, status, context)
           VALUES (1, 'debt_collection', NULL, ?, 'pending', ?)""",
        (5, json.dumps({
            "amount": repayment,
            "original_loan": amount,
            "deadline_turn": deadline,
        }))
    )
    
    return {
        "event_id": event_id,
        "event_type": "underground_loan",
        "outcome": "success",
        "narrative": f"你从地下钱庄借到了 ¥{amount:,.0f}，需要在5回合内还款 ¥{repayment:,.0f}。",
        "state_changes": {
            "cash_delta": amount,
            "debt_added": repayment,
            "deadline": deadline,
        },
    }


def _handle_sec_inquiry(
    conn: sqlite3.Connection,
    event_id: int,
    target_id: int,
    context: dict
) -> dict:
    """
    处理SEC问询事件
    
    Args:
        conn: 数据库连接
        event_id: 事件ID
        target_id: 目标Stock ID
        context: 上下文（包含问询原因等）
    
    Returns:
        dict: 事件结果
    """
    # SEC问询：降低监管热度，但可能罚款
    conn.execute(
        "UPDATE Player SET sec_heat=MAX(0, sec_heat-10) WHERE id=1"
    )
    
    # 小概率罚款
    if random.random() < 0.3:
        player = conn.execute("SELECT cash FROM Player WHERE id=1").fetchone()
        fine = min(player["cash"] * 0.1, 50_000)
        conn.execute(
            "UPDATE Player SET cash=cash-? WHERE id=1",
            (fine,)
        )
        
        return {
            "event_id": event_id,
            "event_type": "sec_inquiry",
            "outcome": "failure",
            "narrative": f"SEC对你的交易进行了调查，虽然未发现违规，但仍被罚款 ¥{fine:,.0f}。",
            "state_changes": {"sec_heat_delta": -10, "fine": fine},
        }
    
    return {
        "event_id": event_id,
        "event_type": "sec_inquiry",
        "outcome": "success",
        "narrative": "SEC对你的交易进行了例行问询，未发现异常。",
        "state_changes": {"sec_heat_delta": -10},
    }


def _handle_debt_collection(
    conn: sqlite3.Connection,
    event_id: int,
    target_id: int,
    context: dict
) -> dict:
    """
    处理地下钱庄追债事件
    
    Args:
        conn: 数据库连接
        event_id: 事件ID
        target_id: 债权人ID（通常为None）
        context: 上下文（包含欠款金额等）
    
    Returns:
        dict: 事件结果
    """
    amount = context.get("amount", 0)
    player = conn.execute("SELECT cash FROM Player WHERE id=1").fetchone()
    
    if player["cash"] >= amount:
        # 有钱还款
        conn.execute(
            "UPDATE Player SET cash=cash-? WHERE id=1",
            (amount,)
        )
        
        return {
            "event_id": event_id,
            "event_type": "debt_collection",
            "outcome": "success",
            "narrative": f"你按时偿还了地下钱庄的债务 ¥{amount:,.0f}。",
            "state_changes": {"cash_delta": -amount},
        }
    else:
        # 无法还款，触发追债事件
        # 强制没收持仓、增加监管热度
        conn.execute(
            "UPDATE Player SET sec_heat=MIN(100, sec_heat+30), in_bankruptcy=1 WHERE id=1"
        )
        
        # 清空持仓
        conn.execute("DELETE FROM Portfolio WHERE player_id=1")
        
        return {
            "event_id": event_id,
            "event_type": "debt_collection",
            "outcome": "failure",
            "narrative": f"你无法偿还债务 ¥{amount:,.0f}，地下钱庄派人上门追债，你的资产被强制没收，监管机构也介入了调查。",
            "state_changes": {
                "sec_heat_delta": 30,
                "in_bankruptcy": True,
                "portfolio_cleared": True,
            },
        }


def _handle_scheme_market_impact(
    conn: sqlite3.Connection,
    event_id: int,
    target_id: int,
    context: dict
) -> dict:
    """
    处理盘外招对股价的影响（博主路线核心事件）

    根据 magnitude 和 direction 影响目标股票价格和    这是社交媒体操作、
    舆论操盘等盘外招对市场的延时影响。

    Args:
        conn: 数据库连接
        event_id: 事件ID
        target_id: 目标股票ID
        context: 上下文（包含 magnitude, description 等）

    Returns:
        dict: 事件结果
    """
    magnitude = context.get("magnitude", 0)
    description = context.get("description", "")

    if not target_id:
        return {
            "event_id": event_id,
            "event_type": "scheme_market_impact",
            "outcome": "failure",
            "narrative": "股价影响事件缺少目标股票",
            "state_changes": {},
        }

    # 获取股票当前价格
    stock = conn.execute(
        "SELECT id, name, current_price FROM Stock WHERE id=?",
        (target_id,)
    ).fetchone()

    if not stock:
        return {
            "event_id": event_id,
            "event_type": "scheme_market_impact",
            "outcome": "failure",
            "narrative": f"目标股票ID {target_id} 不存在",
            "state_changes": {},
        }

    old_price = stock["current_price"]

    # 计算新价格（magnitude 是百分比变化）
    # magnitude 范围：-10.0 ~ +10.0（负数表示下跌，正数表示上涨）
    price_change_percent = magnitude
    new_price = round(old_price * (1 + price_change_percent / 100), 2)
    new_price = max(0.01, new_price)  # 确保价格不为负

    # 更新股价和动量
    conn.execute(
        """UPDATE Stock
           SET current_price = ?,
               hidden_momentum = hidden_momentum + ?
           WHERE id=?""",
        (new_price, magnitude, target_id)
    )

    # 构建叙事
    if magnitude > 0:
        narrative = f"你的市场操作推动 {stock['name']} 上涨了 {abs(magnitude):.1f}%"
    else:
        narrative = f"你的市场操作导致 {stock['name']} 下跌了 {abs(magnitude):.1f}%"

    if description:
        narrative += f"（{description}）"

    return {
        "event_id": event_id,
        "event_type": "scheme_market_impact",
        "outcome": "success",
        "narrative": narrative,
        "state_changes": {
            "target_stock_id": target_id,
            "target_stock_name": stock["name"],
            "old_price": old_price,
            "new_price": new_price,
            "price_change_percent": price_change_percent,
        },
    }


def schedule_event(
    conn: sqlite3.Connection,
    event_type: str,
    target_id: int | None,
    context: dict,
    duration: int | None = None
) -> int:
    """
    创建新的延时事件
    
    Args:
        conn: 数据库连接
        event_type: 事件类型
        target_id: 目标ID（NPC/Stock）
        context: 上下文数据
        duration: 持续回合数（若不指定，从EVENT_TYPE_DURATION获取）
    
    Returns:
        int: 新创建的event_id
    """
    if duration is None:
        duration = EVENT_TYPE_DURATION.get(event_type, 1)
    
    cursor = conn.execute(
        """INSERT INTO ScheduledEvents 
           (player_id, event_type, target_id, turns_remaining, status, context)
           VALUES (1, ?, ?, ?, 'pending', ?)""",
        (event_type, target_id, duration, json.dumps(context, ensure_ascii=False))
    )
    conn.commit()
    
    return cursor.lastrowid
