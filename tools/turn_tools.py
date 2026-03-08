"""
回合推进工具
包含 advance_turn, get_state_snapshot, query_stock_price, get_npc_logs, append_npc_log
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from engines.turn_engine import advance_turn, build_snapshot
from constants import NPC_LOG_MAX_RECORDS


def _json_response(data: dict) -> str:
    """将字典转换为 JSON 字符串"""
    return json.dumps(data, ensure_ascii=False, indent=2)


def _error_response(error_code: str, message: str = "") -> str:
    """生成错误响应"""
    return _json_response({"error": error_code, "message": message})


# ── 回合推进工具 ──────────────────────────────────────

def tool_advance_turn(conn: sqlite3.Connection, story_log: str = "", intents: list = None) -> str:
    """
    MCP 工具：推进回合（改造后整合意图处理）
    
    Args:
        conn: 游戏数据库连接
        story_log: 上回合剧情摘要（100字以内）
        intents: 玩家意图数组
    
    Returns:
        str: JSON 格式的状态快照 + intent_results
    """
    try:
        if intents is None:
            intents = []
        
        snapshot = advance_turn(conn, story_log, intents)
        return _json_response(snapshot)
        
    except Exception as e:
        return _error_response("ADVANCE_TURN_FAILED", str(e))


# ── 状态查询工具（纯只读）──────────────────────────────────────

def tool_get_state_snapshot(conn: sqlite3.Connection) -> str:
    """
    MCP 工具：获取当前状态快照（纯只读，不推进回合）
    
    用于：
    - 新对话恢复上下文
    - 玩家查询状态
    - 确认操作前检查余额
    
    Returns:
        str: JSON 格式的完整状态快照 + 最近5回合剧情 + 总净值
    """
    try:
        # 读取元数据
        meta_rows = conn.execute("SELECT key, value FROM GameMeta").fetchall()
        meta = {row["key"]: row["value"] for row in meta_rows}
        current_turn = int(meta.get("current_turn", 0))
        
        # 玩家信息
        player = conn.execute("SELECT * FROM Player WHERE id=1").fetchone()
        if not player:
            return _error_response("NO_PLAYER", "玩家未初始化")
        
        # 计算总净值（cash + 持仓市值）
        holdings = conn.execute(
            """SELECT p.stock_id, p.quantity, p.avg_cost, s.current_price, s.name
               FROM Portfolio p
               JOIN Stock s ON p.stock_id = s.id
               WHERE p.player_id=1 AND p.quantity>0"""
        ).fetchall()
        
        portfolio_value = 0.0
        portfolio_detail = []
        for h in holdings:
            market_value = h["quantity"] * h["current_price"]
            cost_basis = h["quantity"] * h["avg_cost"]
            unrealized_pnl = market_value - cost_basis
            
            portfolio_value += market_value
            portfolio_detail.append({
                "stock_id": h["stock_id"],
                "stock_name": h["name"],
                "quantity": h["quantity"],
                "avg_cost": h["avg_cost"],
                "current_price": h["current_price"],
                "market_value": round(market_value, 2),
                "unrealized_pnl": round(unrealized_pnl, 2),
            })
        
        total_net_worth = round(player["cash"] + portfolio_value, 2)
        
        # 活跃宏观趋势
        trends = conn.execute(
            """SELECT name, description, industry_tag, direction
               FROM MacroTrends
               WHERE is_active=1 AND (end_turn=-1 OR end_turn>=?)
               AND start_turn<=?""",
            (current_turn, current_turn)
        ).fetchall()
        
        active_trends = [dict(t) for t in trends]
        
        # 最近5回合剧情日志
        recent_logs = conn.execute(
            "SELECT turn, summary FROM ActionLog ORDER BY turn DESC LIMIT 5"
        ).fetchall()
        story_context = [{"turn": log["turn"], "summary": log["summary"]} for log in recent_logs]
        story_context.reverse()  # 按时间正序
        
        # 职位信息
        job_name = None
        if player["current_job_company_id"]:
            stock = conn.execute(
                "SELECT name FROM Stock WHERE id=?",
                (player["current_job_company_id"],)
            ).fetchone()
            if stock:
                job_name = f"Level-{player['job_level']} @ {stock['name']}"
        
        return _json_response({
            "turn": current_turn,
            "calendar": {
                "week": current_turn,
                "month": (current_turn - 1) // 4 + 1 if current_turn > 0 else 1,
                "quarter": ((current_turn - 1) // 4) // 3 + 1 if current_turn > 0 else 1,
            },
            "player": {
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
            },
            "portfolio": portfolio_detail,
            "total_net_worth": total_net_worth,
            "active_trends": active_trends,
            "recent_story": story_context,
        })
    
    except Exception as e:
        return _error_response("GET_STATE_SNAPSHOT_FAILED", str(e))


# ── 股票查询工具 ──────────────────────────────────────

def tool_query_stock_price(conn: sqlite3.Connection, ticker: str) -> str:
    """
    MCP 工具：查询股票价格
    
    Args:
        conn: 游戏数据库连接
        ticker: 股票名称或ID
    
    Returns:
        str: JSON 格式的股票信息（不包含隐藏属性）
    """
    try:
        # 尝试按名称查询
        stock = conn.execute(
            """SELECT id, name, industry_tag, description, current_price, is_revealed
               FROM Stock WHERE name LIKE ?""",
            (f"%{ticker}%",)
        ).fetchone()
        
        # 若无结果，尝试按ID查询
        if not stock:
            try:
                stock_id = int(ticker)
                stock = conn.execute(
                    """SELECT id, name, industry_tag, description, current_price, is_revealed
                       FROM Stock WHERE id=?""",
                    (stock_id,)
                ).fetchone()
            except ValueError:
                pass
        
        if not stock:
            return _error_response("STOCK_NOT_FOUND", f"未找到股票: {ticker}")
        
        return _json_response({
            "id": stock["id"],
            "name": stock["name"],
            "price": stock["current_price"],
            "industry_tag": stock["industry_tag"],
            "description": stock["description"],
            "is_revealed": bool(stock["is_revealed"])
        })
        
    except Exception as e:
        return _error_response("QUERY_STOCK_FAILED", str(e))


# ── 市场看板工具 ──────────────────────────────────────

def tool_list_market(conn: sqlite3.Connection) -> str:
    """
    MCP 工具：获取全市场股票看板
    
    返回所有股票的当前行情，同时标注玩家持仓情况。
    不包含任何隐藏属性。
    
    Returns:
        str: JSON 格式的市场看板
    """
    try:
        stocks = conn.execute(
            """SELECT id, name, industry_tag, description, current_price, is_revealed
               FROM Stock ORDER BY industry_tag, id"""
        ).fetchall()
        
        # 查询玩家持仓，构建 stock_id → {quantity, avg_cost} 映射
        holdings = conn.execute(
            "SELECT stock_id, quantity, avg_cost FROM Portfolio WHERE player_id=1 AND quantity>0"
        ).fetchall()
        holding_map = {row["stock_id"]: row for row in holdings}
        
        market = []
        for s in stocks:
            item = {
                "id":           s["id"],
                "name":         s["name"],
                "industry_tag": s["industry_tag"],
                "price":        s["current_price"],
                "is_revealed":  bool(s["is_revealed"]),
            }
            if s["id"] in holding_map:
                h = holding_map[s["id"]]
                item["holding"] = {
                    "quantity": h["quantity"],
                    "avg_cost": h["avg_cost"],
                    "unrealized_pnl": round(
                        (s["current_price"] - h["avg_cost"]) * h["quantity"], 2
                    ),
                }
            market.append(item)
        
        return _json_response({
            "total": len(market),
            "market": market,
        })
    
    except Exception as e:
        return _error_response("LIST_MARKET_FAILED", str(e))


# ── NPC 日志工具 ──────────────────────────────────────

def tool_get_npc_logs(conn: sqlite3.Connection, npc_id: int, limit: int = 10) -> str:
    """
    MCP 工具：获取 NPC 交互日志
    
    Args:
        conn: 游戏数据库连接
        npc_id: NPC ID
        limit: 最多返回条数
    
    Returns:
        str: JSON 格式的 NPC 信息和日志
    """
    try:
        # 查询 NPC 基本信息
        npc = conn.execute(
            """SELECT npc_id, company_id, name, role, bribe_resistance, 
                      alertness, relationship_with_player
               FROM CompanyNPC WHERE npc_id=?""",
            (npc_id,)
        ).fetchone()
        
        if not npc:
            return _error_response("NPC_NOT_FOUND", f"未找到 NPC: {npc_id}")
        
        # 查询交互日志
        logs = conn.execute(
            """SELECT turn, summary FROM NpcInteractionLog 
               WHERE npc_id=? ORDER BY turn DESC LIMIT ?""",
            (npc_id, limit)
        ).fetchall()
        
        return _json_response({
            "npc_id": npc["npc_id"],
            "npc_name": npc["name"],
            "role": npc["role"],
            "relationship": npc["relationship_with_player"],
            "alertness": npc["alertness"],
            "logs": [{"turn": log["turn"], "summary": log["summary"]} for log in logs]
        })
        
    except Exception as e:
        return _error_response("GET_NPC_LOGS_FAILED", str(e))


def tool_append_npc_log(conn: sqlite3.Connection, npc_id: int, turn: int, summary: str) -> str:
    """
    MCP 工具：追加 NPC 交互日志
    
    Args:
        conn: 游戏数据库连接
        npc_id: NPC ID
        turn: 当前回合数
        summary: 交互摘要（≤100字）
    
    Returns:
        str: JSON 格式的响应
    """
    try:
        # 检查 NPC 是否存在
        npc = conn.execute(
            "SELECT npc_id FROM CompanyNPC WHERE npc_id=?",
            (npc_id,)
        ).fetchone()
        
        if not npc:
            return _error_response("NPC_NOT_FOUND", f"未找到 NPC: {npc_id}")
        
        # 插入日志
        cursor = conn.execute(
            "INSERT INTO NpcInteractionLog (npc_id, turn, summary) VALUES (?, ?, ?)",
            (npc_id, turn, summary)
        )
        
        log_id = cursor.lastrowid
        
        # 检查并清理超出上限的记录
        count = conn.execute(
            "SELECT COUNT(*) as cnt FROM NpcInteractionLog WHERE npc_id=?",
            (npc_id,)
        ).fetchone()["cnt"]
        
        if count > NPC_LOG_MAX_RECORDS:
            # 删除最旧的记录
            conn.execute(
                """DELETE FROM NpcInteractionLog 
                   WHERE npc_id=? AND log_id NOT IN (
                       SELECT log_id FROM NpcInteractionLog 
                       WHERE npc_id=? ORDER BY turn DESC LIMIT ?
                   )""",
                (npc_id, npc_id, NPC_LOG_MAX_RECORDS)
            )
        
        conn.commit()
        
        return _json_response({
            "log_id": log_id,
            "message": f"已记录与 NPC {npc_id} 的交互"
        })

    except Exception as e:
        return _error_response("APPEND_NPC_LOG_FAILED", str(e))


def tool_investigate_abnormal_movement(conn: sqlite3.Connection, stock_id: int) -> str:
    """
    MCP 工具：调查股票异常资金流动

    Args:
        conn: 游戏数据库连接
        stock_id: 股票 ID

    Returns:
        str: JSON 格式的调查结果显示
    """
    try:
        stock = conn.execute(
            "SELECT id, name FROM Stock WHERE id=?",
            (stock_id,)
        ).fetchone()

        if not stock:
            return _error_response("STOCK_NOT_FOUND", f"未找到股票: {stock_id}")

        recent_traces = conn.execute(
            """SELECT turn, trace_type, content FROM MarketTrace
               WHERE stock_id=? AND trace_type='rumor'
               ORDER BY turn DESC LIMIT 5""",
            (stock_id,)
        ).fetchall()

        if not recent_traces:
            return _json_response({
                "stock_id": stock_id,
                "stock_name": stock["name"],
                "rumors": [],
                "message": "未发现任何异常资金流动的传言"
            })

        rumors = [
            {
                "turn": t["turn"],
                "content": t["content"]
            }
            for t in recent_traces
        ]

        return _json_response({
            "stock_id": stock_id,
            "stock_name": stock["name"],
            "rumors": rumors,
            "message": f"发现 {len(rumors)} 条相关传言"
        })

    except Exception as e:
        return _error_response("INVESTIGATE_FAILED", str(e))
