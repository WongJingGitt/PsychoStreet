import json
import random
import sqlite3
from typing import Any


def _json_response(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False)


def _error_response(error_code: str, message: str = "") -> str:
    return json.dumps({"error": error_code, "message": message}, ensure_ascii=False)


def acquire_item(
    conn: sqlite3.Connection,
    item_name: str,
    category_tag: str,
    description: str,
    estimated_cost: float,
    current_turn: int,
    feasibility_tier: str = "normal"
) -> str:
    """
    获取/购买物品
    
    Args:
        conn: 游戏数据库连接
        item_name: 物品名称
        category_tag: 语义化标签 (e.g. "重资产", "致命黑料", "暗网凭证")
        description: 详细描述
        estimated_cost: 预估成本
        current_turn: 当前回合
        feasibility_tier: 现实可行性档位
    
    Returns:
        str: JSON 格式的响应
    """
    try:
        player = conn.execute("SELECT cash FROM Player WHERE id=1").fetchone()
        if not player:
            return _error_response("PLAYER_NOT_FOUND", "玩家不存在")
        
        if player["cash"] < estimated_cost:
            return _error_response(
                "INSUFFICIENT_CASH",
                f"你的现金 {player['cash']:.0f} 不足以支付 {estimated_cost:.0f} 的费用"
            )
        
        success = True
        if feasibility_tier == "impossible":
            success = False
        elif feasibility_tier == "hard":
            success = random.random() < 0.3
        elif feasibility_tier == "normal":
            success = random.random() < 0.7
        elif feasibility_tier == "easy":
            success = random.random() < 0.9
        elif feasibility_tier == "trivial":
            success = True
        
        if not success:
            conn.execute(
                "UPDATE Player SET cash = cash - ? WHERE id=1",
                (estimated_cost * 0.1,)
            )
            conn.commit()
            return _json_response({
                "success": False,
                "outcome": "failed",
                "item_name": item_name,
                "narrative": f"你尝试获取 {item_name}，但行动失败了，还损失了 {estimated_cost * 0.1:.0f} 的手续费。"
            })
        
        conn.execute(
            "UPDATE Player SET cash = cash - ? WHERE id=1",
            (estimated_cost,)
        )
        
        conn.execute(
            """INSERT INTO PlayerInventory 
               (player_id, name, category_tag, description, estimated_value, status, acquire_turn)
               VALUES (1, ?, ?, ?, ?, '正常持有', ?)""",
            (item_name, category_tag, description, estimated_cost, current_turn)
        )
        
        conn.commit()
        
        return _json_response({
            "success": True,
            "outcome": "acquired",
            "item_name": item_name,
            "category_tag": category_tag,
            "cash_spent": estimated_cost,
            "narrative": f"你成功获得了 {item_name}（{category_tag}）：{description}"
        })
    
    except Exception as e:
        return _error_response("ACQUIRE_ITEM_FAILED", str(e))


def update_item_status(
    conn: sqlite3.Connection,
    item_id: int,
    new_status: str
) -> str:
    """
    修改物品的语义状态
    
    Args:
        conn: 游戏数据库连接
        item_id: 物品ID
        new_status: 新状态（语义化描述）
    
    Returns:
        str: JSON 格式的响应
    """
    try:
        item = conn.execute(
            "SELECT * FROM PlayerInventory WHERE item_id=? AND player_id=1",
            (item_id,)
        ).fetchone()
        
        if not item:
            return _error_response("ITEM_NOT_FOUND", f"物品 ID {item_id} 不存在")
        
        debt = conn.execute(
            "SELECT * FROM PlayerDebts WHERE collateral_item_id=?",
            (item_id,)
        ).fetchone()
        
        if debt:
            return _error_response(
                "ITEM_COLLATERALIZED",
                f"该物品已被抵押，无法修改状态。先偿还债务。"
            )
        
        old_status = item["status"]
        conn.execute(
            "UPDATE PlayerInventory SET status=? WHERE item_id=?",
            (new_status, item_id)
        )
        conn.commit()
        
        return _json_response({
            "success": True,
            "outcome": "status_updated",
            "item_id": item_id,
            "item_name": item["name"],
            "old_status": old_status,
            "new_status": new_status,
            "narrative": f"你将 {item['name']} 的状态从「{old_status}」变更为「{new_status}」"
        })
    
    except Exception as e:
        return _error_response("UPDATE_ITEM_STATUS_FAILED", str(e))


def consume_item(
    conn: sqlite3.Connection,
    item_id: int,
    cash_gained: float = 0.0,
    reason: str = ""
) -> str:
    """
    消耗/销毁/售出物品
    
    Args:
        conn: 游戏数据库连接
        item_id: 物品ID
        cash_gained: 获得的现金（如果是卖出变现）
        reason: 消耗原因
    
    Returns:
        str: JSON 格式的响应
    """
    try:
        item = conn.execute(
            "SELECT * FROM PlayerInventory WHERE item_id=? AND player_id=1",
            (item_id,)
        ).fetchone()
        
        if not item:
            return _error_response("ITEM_NOT_FOUND", f"物品 ID {item_id} 不存在")
        
        debt = conn.execute(
            "SELECT * FROM PlayerDebts WHERE collateral_item_id=?",
            (item_id,)
        ).fetchone()
        
        if debt:
            return _error_response(
                "ITEM_COLLATERALIZED",
                f"该物品已被抵押，无法处置。先偿还债务。"
            )
        
        if cash_gained > 0:
            conn.execute(
                "UPDATE Player SET cash = cash + ? WHERE id=1",
                (cash_gained,)
            )
        
        conn.execute(
            "DELETE FROM PlayerInventory WHERE item_id=?",
            (item_id,)
        )
        conn.commit()
        
        if cash_gained > 0:
            narrative = f"你将 {item['name']} 售出，获得 ${cash_gained:,.0f}。"
        else:
            narrative = f"你消耗了 {item['name']}：{reason}"
        
        return _json_response({
            "success": True,
            "outcome": "consumed",
            "item_id": item_id,
            "item_name": item["name"],
            "cash_gained": cash_gained,
            "narrative": narrative
        })
    
    except Exception as e:
        return _error_response("CONSUME_ITEM_FAILED", str(e))


def take_loan(
    conn: sqlite3.Connection,
    collateral_item_id: int,
    loan_amount: float,
    duration_turns: int,
    current_turn: int
) -> str:
    """
    抵押借款
    
    Args:
        conn: 游戏数据库连接
        collateral_item_id: 抵押物ID
        loan_amount: 借款金额
        duration_turns: 借款期限（回合数）
        current_turn: 当前回合
    
    Returns:
        str: JSON 格式的响应
    """
    try:
        player = conn.execute("SELECT cash FROM Player WHERE id=1").fetchone()
        if not player:
            return _error_response("PLAYER_NOT_FOUND", "玩家不存在")
        
        item = conn.execute(
            "SELECT * FROM PlayerInventory WHERE item_id=? AND player_id=1",
            (collateral_item_id,)
        ).fetchone()
        
        if not item:
            return _error_response("ITEM_NOT_FOUND", f"物品 ID {collateral_item_id} 不存在")
        
        existing_debt = conn.execute(
            "SELECT * FROM PlayerDebts WHERE collateral_item_id=?",
            (collateral_item_id,)
        ).fetchone()
        
        if existing_debt:
            return _error_response(
                "ITEM_ALREADY_COLLATERALIZED",
                f"该物品已经是抵押物，无法重复抵押"
            )
        
        if item["estimated_value"] < loan_amount * 0.5:
            return _error_response(
                "INSUFFICIENT_COLLATERAL",
                f"物品估值 ${item['estimated_value']:,.0f} 不足以抵押 ${loan_amount:,.0f}。至少需要估值 50% 的抵押物。"
            )
        
        due_turn = current_turn + duration_turns
        
        conn.execute(
            """INSERT INTO PlayerDebts 
               (player_id, debt_type, amount_owed, collateral_item_id, due_turn)
               VALUES (1, 'cash_loan', ?, ?, ?)""",
            (loan_amount, collateral_item_id, due_turn)
        )
        
        conn.execute(
            "UPDATE Player SET cash = cash + ? WHERE id=1",
            (loan_amount,)
        )
        
        conn.execute(
            "UPDATE PlayerInventory SET status = '已抵押，冻结中' WHERE item_id = ?",
            (collateral_item_id,)
        )
        
        conn.commit()
        
        return _json_response({
            "success": True,
            "outcome": "loan_taken",
            "debt_type": "cash_loan",
            "loan_amount": loan_amount,
            "collateral_item_id": collateral_item_id,
            "item_name": item["name"],
            "due_turn": due_turn,
            "duration_turns": duration_turns,
            "narrative": f"你将 {item['name']}（估值 ${item['estimated_value']:,.0f}）抵押给地下钱庄，获得 ${loan_amount:,.0f} 贷款。必须在 {duration_turns} 回合内偿还。"
        })
    
    except Exception as e:
        return _error_response("TAKE_LOAN_FAILED", str(e))


def repay_loan(
    conn: sqlite3.Connection,
    debt_id: int
) -> str:
    """
    偿还借款
    
    Args:
        conn: 游戏数据库连接
        debt_id: 债务ID
    
    Returns:
        str: JSON 格式的响应
    """
    try:
        player = conn.execute("SELECT cash FROM Player WHERE id=1").fetchone()
        if not player:
            return _error_response("PLAYER_NOT_FOUND", "玩家不存在")
        
        debt = conn.execute(
            "SELECT * FROM PlayerDebts WHERE debt_id=? AND player_id=1",
            (debt_id,)
        ).fetchone()
        
        if not debt:
            return _error_response("DEBT_NOT_FOUND", f"债务 ID {debt_id} 不存在")
        
        if player["cash"] < debt["amount_owed"]:
            return _error_response(
                "INSUFFICIENT_CASH",
                f"你的现金 ${player['cash']:,.0f} 不足以偿还 ${debt['amount_owed']:,.0f} 的债务"
            )
        
        conn.execute(
            "UPDATE Player SET cash = cash - ? WHERE id=1",
            (debt["amount_owed"],)
        )
        
        if debt["collateral_item_id"]:
            conn.execute(
                "UPDATE PlayerInventory SET status = '正常持有' WHERE item_id = ?",
                (debt["collateral_item_id"],)
            )
        
        conn.execute(
            "DELETE FROM PlayerDebts WHERE debt_id=?",
            (debt_id,)
        )
        
        conn.commit()
        
        item_name = None
        if debt["collateral_item_id"]:
            item = conn.execute(
                "SELECT name FROM PlayerInventory WHERE item_id=?",
                (debt["collateral_item_id"],)
            ).fetchone()
            if item:
                item_name = item["name"]
        
        narrative = f"你偿还了 ${debt['amount_owed']:,.0f} 的贷款。"
        if item_name:
            narrative += f" {item_name} 已解除抵押。"
        
        return _json_response({
            "success": True,
            "outcome": "loan_repaid",
            "debt_id": debt_id,
            "amount_paid": debt["amount_owed"],
            "collateral_released": debt["collateral_item_id"] is not None,
            "item_name": item_name,
            "narrative": narrative
        })
    
    except Exception as e:
        return _error_response("REPAY_LOAN_FAILED", str(e))


# ── MCP 工具封装 ──────────────────────────────────────

def tool_acquire_item(
    conn: sqlite3.Connection,
    current_turn: int,
    item_name: str,
    category_tag: str,
    description: str,
    estimated_cost: float,
    feasibility_tier: str = "normal"
) -> str:
    """MCP 工具：获取/购买物品"""
    if conn is None:
        return _error_response("NO_ACTIVE_GAME", "没有激活的游戏")
    return acquire_item(
        conn, item_name, category_tag, description,
        estimated_cost, current_turn, feasibility_tier
    )


def tool_update_item_status(conn: sqlite3.Connection, item_id: int, new_status: str) -> str:
    """MCP 工具：修改物品状态"""
    if conn is None:
        return _error_response("NO_ACTIVE_GAME", "没有激活的游戏")
    return update_item_status(conn, item_id, new_status)


def tool_consume_item(conn: sqlite3.Connection, item_id: int, cash_gained: float = 0.0, reason: str = "") -> str:
    """MCP 工具：消耗/售出物品"""
    if conn is None:
        return _error_response("NO_ACTIVE_GAME", "没有激活的游戏")
    return consume_item(conn, item_id, cash_gained, reason)


def tool_take_loan(
    conn: sqlite3.Connection,
    current_turn: int,
    collateral_item_id: int,
    loan_amount: float,
    duration_turns: int
) -> str:
    """MCP 工具：抵押借款"""
    if conn is None:
        return _error_response("NO_ACTIVE_GAME", "没有激活的游戏")
    return take_loan(
        conn, collateral_item_id, loan_amount,
        duration_turns, current_turn
    )


def tool_repay_loan(conn: sqlite3.Connection, debt_id: int) -> str:
    """MCP 工具：偿还借款"""
    if conn is None:
        return _error_response("NO_ACTIVE_GAME", "没有激活的游戏")
    return repay_loan(conn, debt_id)
