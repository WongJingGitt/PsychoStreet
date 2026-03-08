"""
ActionLog工具
负责记录玩家每回合的核心操作摘要，生成人物传记式的长期记忆
"""

import json
import sqlite3

from constants import ACTIONLOG_MAX_LENGTH, ACTIONLOG_MAX_RECORDS


def append_action_log(
    conn: sqlite3.Connection,
    turn: int,
    summary: str
) -> dict:
    """
    追加一条ActionLog记录
    
    Args:
        conn: 游戏数据库连接
        turn: 当前回合数
        summary: 操作摘要（由LLM生成，≤200字）
    
    Returns:
        dict: 包含log_id和确认信息
    """
    # 截断过长的摘要
    if len(summary) > ACTIONLOG_MAX_LENGTH:
        summary = summary[:ACTIONLOG_MAX_LENGTH - 3] + "..."
    
    cursor = conn.execute(
        "INSERT INTO ActionLog (turn, summary) VALUES (?, ?)",
        (turn, summary)
    )
    
    # 检查总记录数，删除超出上限的旧记录
    total = conn.execute("SELECT COUNT(*) as count FROM ActionLog").fetchone()["count"]
    
    if total > ACTIONLOG_MAX_RECORDS:
        # 删除最旧的记录
        conn.execute(
            f"""DELETE FROM ActionLog 
               WHERE log_id IN (
                   SELECT log_id FROM ActionLog 
                   ORDER BY log_id ASC 
                   LIMIT ?
               )""",
            (total - ACTIONLOG_MAX_RECORDS,)
        )
    
    conn.commit()
    
    return {
        "log_id": cursor.lastrowid,
        "turn": turn,
        "summary": summary,
        "message": f"已记录第{turn}回合的操作摘要"
    }


def get_action_logs(
    conn: sqlite3.Connection,
    limit: int = 20
) -> dict:
    """
    获取ActionLog列表
    
    Args:
        conn: 游戏数据库连接
        limit: 最多返回条数，默认20
    
    Returns:
        dict: 包含logs列表
    """
    logs = conn.execute(
        """SELECT log_id, turn, summary 
           FROM ActionLog 
           ORDER BY turn DESC 
           LIMIT ?""",
        (limit,)
    ).fetchall()
    
    return {
        "logs": [
            {
                "log_id": log["log_id"],
                "turn": log["turn"],
                "summary": log["summary"]
            }
            for log in logs
        ],
        "count": len(logs)
    }


def get_action_log_by_turn(
    conn: sqlite3.Connection,
    turn: int
) -> dict | None:
    """
    获取指定回合的ActionLog
    
    Args:
        conn: 游戏数据库连接
        turn: 回合数
    
    Returns:
        dict | None: ActionLog记录，若不存在则返回None
    """
    log = conn.execute(
        "SELECT log_id, turn, summary FROM ActionLog WHERE turn=?",
        (turn,)
    ).fetchone()
    
    if not log:
        return None
    
    return {
        "log_id": log["log_id"],
        "turn": log["turn"],
        "summary": log["summary"]
    }


def get_biography(conn: sqlite3.Connection) -> dict:
    """
    获取完整的人物传记（所有ActionLog）
    
    Args:
        conn: 游戏数据库连接
    
    Returns:
        dict: 包含完整传记文本和日志列表
    """
    logs = conn.execute(
        """SELECT turn, summary 
           FROM ActionLog 
           ORDER BY turn ASC"""
    ).fetchall()
    
    if not logs:
        return {
            "biography": "暂无记录",
            "total_turns": 0
        }
    
    # 构建传记文本
    biography_lines = []
    for log in logs:
        biography_lines.append(f"第{log['turn']}周：{log['summary']}")
    
    biography = "\n".join(biography_lines)
    
    return {
        "biography": biography,
        "total_turns": len(logs),
        "logs": [dict(log) for log in logs]
    }


def clear_action_logs(conn: sqlite3.Connection) -> dict:
    """
    清空所有ActionLog（用于重新开始）
    
    Args:
        conn: 游戏数据库连接
    
    Returns:
        dict: 操作结果
    """
    conn.execute("DELETE FROM ActionLog")
    conn.commit()
    
    return {
        "success": True,
        "message": "已清空所有操作日志"
    }
