"""
交易工具
包含 buy_stock, sell_stock
"""

import json
import sqlite3
from typing import Any

from constants import (
    TRADE_HEAT_LOW_RATIO,
    TRADE_HEAT_MID_RATIO,
    TRADE_HEAT_HIGH_RATIO,
    TRADE_HEAT_LOW_DELTA,
    TRADE_HEAT_MID_DELTA,
    TRADE_HEAT_HIGH_DELTA,
)


def _json_response(data: dict) -> str:
    """将字典转换为 JSON 字符串"""
    return json.dumps(data, ensure_ascii=False, indent=2)


def _error_response(error_code: str, message: str = "") -> str:
    """生成错误响应"""
    return _json_response({"error": error_code, "message": message})


def _calculate_trade_heat(total_cost: float, liquidity: float) -> tuple[int, str]:
    """
    计算交易异动热度

    Args:
        total_cost: 交易金额
        liquidity: 股票流动性

    Returns:
        tuple[int, str]: (热度增量, 是否触发SEC问询)
    """
    if liquidity <= 0:
        return 0, ""

    trade_ratio = total_cost / liquidity

    if trade_ratio >= TRADE_HEAT_HIGH_RATIO:
        return TRADE_HEAT_HIGH_DELTA, "HIGH"
    elif trade_ratio >= TRADE_HEAT_MID_RATIO:
        return TRADE_HEAT_MID_DELTA, "MID"
    elif trade_ratio >= TRADE_HEAT_LOW_RATIO:
        return TRADE_HEAT_LOW_DELTA, "LOW"

    return 0, ""


def tool_buy_stock(conn: sqlite3.Connection, stock_id: int, quantity: int) -> str:
    """
    MCP 工具：买入股票

    Args:
        conn: 游戏数据库连接
        stock_id: 股票ID
        quantity: 买入数量

    Returns:
        str: JSON 格式的交易结果
    """
    try:
        # 参数验证
        if quantity <= 0:
            return _error_response("INVALID_QUANTITY", "买入数量必须大于0")

        # 查询股票信息（包含退市状态）
        stock = conn.execute(
            "SELECT id, name, current_price, hidden_liquidity, is_delisted FROM Stock WHERE id=?",
            (stock_id,)
        ).fetchone()

        if not stock:
            return _error_response("STOCK_NOT_FOUND", f"未找到股票ID: {stock_id}")

        # 检查股票是否已退市
        if stock["is_delisted"]:
            return _error_response("STOCK_DELISTED",
                f"股票 {stock['name']} 已退市，无法买入")

        # 查询玩家资金
        player = conn.execute("SELECT cash FROM Player WHERE id=1").fetchone()

        if not player:
            return _error_response("NO_PLAYER", "未找到玩家")

        # 计算总成本
        total_cost = stock["current_price"] * quantity

        # 检查资金是否足够
        if player["cash"] < total_cost:
            return _error_response("INSUFFICIENT_CASH",
                f"资金不足：需要 {total_cost:,.2f}，当前 {player['cash']:,.2f}")

        # 计算交易异动热度
        sec_heat_delta, heat_level = _calculate_trade_heat(total_cost, stock["hidden_liquidity"])

        # 扣除资金
        conn.execute(
            "UPDATE Player SET cash=cash-?, sec_heat=MIN(100, sec_heat+?) WHERE id=1",
            (total_cost, sec_heat_delta)
        )

        # 更新或创建持仓记录
        portfolio = conn.execute(
            "SELECT quantity, avg_cost FROM Portfolio WHERE player_id=1 AND stock_id=?",
            (stock_id,)
        ).fetchone()

        if portfolio:
            # 计算新的平均成本
            new_quantity = portfolio["quantity"] + quantity
            new_avg_cost = (
                (portfolio["avg_cost"] * portfolio["quantity"] + total_cost) / new_quantity
            )

            conn.execute(
                "UPDATE Portfolio SET quantity=?, avg_cost=? WHERE player_id=1 AND stock_id=?",
                (new_quantity, new_avg_cost, stock_id)
            )
        else:
            # 创建新持仓
            avg_cost = total_cost / quantity
            conn.execute(
                "INSERT INTO Portfolio (player_id, stock_id, quantity, avg_cost) VALUES (1, ?, ?, ?)",
                (stock_id, quantity, avg_cost)
            )

        # 检查是否触发 SEC 问询事件
        if heat_level == "HIGH":
            conn.execute(
                """INSERT INTO ScheduledEvents
                   (player_id, event_type, target_id, turns_remaining, status, context)
                   VALUES (1, 'sec_inquiry', ?, 1, 'pending', '{}')""",
                (stock_id,)
            )

        # 查询更新后的资金
        new_cash = conn.execute("SELECT cash FROM Player WHERE id=1").fetchone()["cash"]

        conn.commit()

        result = {
            "success": True,
            "stock_name": stock["name"],
            "quantity": quantity,
            "price": stock["current_price"],
            "total_cost": total_cost,
            "remaining_cash": new_cash,
            "sec_heat_delta": sec_heat_delta,
        }

        if heat_level == "HIGH":
            result["warning"] = "交易异动过大，已触发SEC关注"
        elif heat_level == "MID":
            result["warning"] = "交易异动较大，监管雷达出现波动"

        return _json_response(result)

    except Exception as e:
        return _error_response("BUY_STOCK_FAILED", str(e))


def tool_sell_stock(conn: sqlite3.Connection, stock_id: int, quantity: int) -> str:
    """
    MCP 工具：卖出股票

    Args:
        conn: 游戏数据库连接
        stock_id: 股票ID
        quantity: 卖出数量（-1 表示全部卖出）

    Returns:
        str: JSON 格式的交易结果
    """
    try:
        # 查询股票信息（包含退市状态）
        stock = conn.execute(
            "SELECT id, name, current_price, hidden_liquidity, is_delisted FROM Stock WHERE id=?",
            (stock_id,)
        ).fetchone()

        if not stock:
            return _error_response("STOCK_NOT_FOUND", f"未找到股票ID: {stock_id}")

        # 检查股票是否已退市（退市股票允许卖出，但会在退市时自动清算）
        if stock["is_delisted"]:
            return _error_response("STOCK_DELISTED",
                f"股票 {stock['name']} 已退市，持仓已自动清算")

        # 查询持仓
        portfolio = conn.execute(
            "SELECT quantity, avg_cost FROM Portfolio WHERE player_id=1 AND stock_id=?",
            (stock_id,)
        ).fetchone()

        if not portfolio or portfolio["quantity"] == 0:
            return _error_response("NO_POSITION", "未持有该股票")

        # 处理 -1（全部卖出）
        if quantity == -1:
            quantity = portfolio["quantity"]

        # 参数验证
        if quantity <= 0:
            return _error_response("INVALID_QUANTITY", "卖出数量必须大于0或-1")

        if quantity > portfolio["quantity"]:
            return _error_response("INSUFFICIENT_POSITION",
                f"持仓不足：需要 {quantity}，当前 {portfolio['quantity']}")

        # 计算收入和盈亏
        proceeds = stock["current_price"] * quantity
        cost_basis = portfolio["avg_cost"] * quantity
        profit_loss = proceeds - cost_basis

        # 计算交易异动热度
        sec_heat_delta, heat_level = _calculate_trade_heat(proceeds, stock["hidden_liquidity"])

        # 增加资金
        conn.execute(
            "UPDATE Player SET cash=cash+?, sec_heat=MIN(100, sec_heat+?) WHERE id=1",
            (proceeds, sec_heat_delta)
        )

        # 更新持仓
        new_quantity = portfolio["quantity"] - quantity

        if new_quantity == 0:
            # 清空持仓
            conn.execute(
                "DELETE FROM Portfolio WHERE player_id=1 AND stock_id=?",
                (stock_id,)
            )
        else:
            # 减少持仓
            conn.execute(
                "UPDATE Portfolio SET quantity=? WHERE player_id=1 AND stock_id=?",
                (new_quantity, stock_id)
            )

        # 检查是否触发 SEC 问询事件
        if heat_level == "HIGH":
            conn.execute(
                """INSERT INTO ScheduledEvents
                   (player_id, event_type, target_id, turns_remaining, status, context)
                   VALUES (1, 'sec_inquiry', ?, 1, 'pending', '{}')""",
                (stock_id,)
            )

        # 查询更新后的资金
        new_cash = conn.execute("SELECT cash FROM Player WHERE id=1").fetchone()["cash"]

        conn.commit()

        result = {
            "success": True,
            "stock_name": stock["name"],
            "quantity_sold": quantity,
            "price": stock["current_price"],
            "proceeds": proceeds,
            "profit_loss": profit_loss,
            "remaining_cash": new_cash,
            "sec_heat_delta": sec_heat_delta,
        }

        if heat_level == "HIGH":
            result["warning"] = "交易异动过大，已触发SEC关注"
        elif heat_level == "MID":
            result["warning"] = "交易异动较大，监管雷达出现波动"

        return _json_response(result)

    except Exception as e:
        return _error_response("SELL_STOCK_FAILED", str(e))
