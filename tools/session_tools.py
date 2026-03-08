"""
游戏会话管理工具
包含 new_game, load_game, list_games, save_checkpoint, load_checkpoint
"""

import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from db import global_db, game_db
from constants import DEFAULT_STARTING_CASH, DEFAULT_COMPANY_COUNT, DEFAULT_TOTAL_TURNS


# ── 工具函数 ──────────────────────────────────────────────

def _json_response(data: dict) -> str:
    """将字典转换为 JSON 字符串"""
    return json.dumps(data, ensure_ascii=False, indent=2)


def _error_response(error_code: str, message: str = "") -> str:
    """生成错误响应"""
    return _json_response({"error": error_code, "message": message})


# ── 会话管理工具实现 ──────────────────────────────────────

def new_game(
    display_name: str,
    starting_cash: float = DEFAULT_STARTING_CASH,
    company_count: int = DEFAULT_COMPANY_COUNT,
    total_turns: int = DEFAULT_TOTAL_TURNS
) -> str:
    """
    创建新游戏实例
    
    Args:
        display_name: 游戏显示名称
        starting_cash: 初始资金
        company_count: 公司数量（暂未使用，仅记录）
        total_turns: 游戏总回合数
    
    Returns:
        str: JSON 格式的响应
    """
    # 参数验证
    if starting_cash <= 0:
        return _error_response("INVALID_STARTING_CASH", "初始资金必须大于0")
    
    try:
        # 获取数据目录
        data_dir = Path(global_db.get_global_db_path()).parent
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        db_filename = f"game_{timestamp}.db"
        db_path = data_dir / db_filename
        
        # 创建游戏数据库
        conn = game_db.create_game_db(db_path)
        
        # 在 global.db 中创建会话记录
        game_id = global_db.create_game_session(
            display_name=display_name,
            db_path=str(db_path)
        )
        
        # 更新激活游戏ID
        global_db.set_active_game_id(game_id)
        
        # 初始化游戏元数据（暂不初始化玩家和公司，等待后续调用 init_* 工具）
        game_db.init_game_meta(conn, player_name="Player", total_turns=total_turns)
        
        conn.commit()
        
        # 注意：不关闭连接，由 main.py 的全局状态管理
        # 返回的连接需要在 main.py 中缓存
        
        return _json_response({
            "game_id": game_id,
            "display_name": display_name,
            "db_path": str(db_path),
            "starting_cash": starting_cash,
            "message": f"游戏 '{display_name}' 已创建，game_id={game_id}"
        })
        
    except Exception as e:
        return _error_response("CREATE_GAME_FAILED", str(e))


def load_game(game_id: int) -> str:
    """
    加载已存在的游戏
    
    Args:
        game_id: 游戏ID
    
    Returns:
        str: JSON 格式的响应
    """
    try:
        # 查询游戏会话
        session = global_db.get_game_session(game_id)
        
        if not session:
            return _error_response("GAME_NOT_FOUND", f"游戏ID {game_id} 不存在")
        
        if session["status"] != "active":
            return _error_response("GAME_NOT_ACTIVE", f"游戏状态为 {session['status']}，无法加载")
        
        # 更新激活游戏ID
        global_db.set_active_game_id(game_id)
        
        # 更新最后游玩时间
        global_db.update_game_session(game_id, session["turn"])
        
        return _json_response({
            "game_id": game_id,
            "display_name": session["display_name"],
            "turn": session["turn"],
            "status": session["status"],
            "message": f"游戏 '{session['display_name']}' 已加载"
        })
        
    except Exception as e:
        return _error_response("LOAD_GAME_FAILED", str(e))


def list_games() -> str:
    """
    列出所有游戏会话
    
    Returns:
        str: JSON 格式的响应
    """
    try:
        sessions = global_db.list_game_sessions()
        
        return _json_response({
            "games": sessions,
            "count": len(sessions)
        })
        
    except Exception as e:
        return _error_response("LIST_GAMES_FAILED", str(e))


def save_checkpoint(tag: str = "") -> str:
    """
    创建存档快照
    
    注意：此函数需要访问当前激活的游戏连接
    在 main.py 中通过闭包或全局变量传递连接
    
    Args:
        tag: 存档备注标签
    
    Returns:
        str: JSON 格式的响应
    """
    # 此函数需要在 main.py 中通过全局状态实现
    # 这里提供接口签名
    raise NotImplementedError("save_checkpoint 需要在 main.py 中实现")


def load_checkpoint(checkpoint_id: int) -> str:
    """
    加载存档快照
    
    注意：此函数需要访问当前激活的游戏连接
    在 main.py 中通过闭包或全局变量传递连接
    
    Args:
        checkpoint_id: 存档ID
    
    Returns:
        str: JSON 格式的响应
    """
    # 此函数需要在 main.py 中通过全局状态实现
    # 这里提供接口签名
    raise NotImplementedError("load_checkpoint 需要在 main.py 中实现")


# ── MCP 工具包装函数 ──────────────────────────────────────

def tool_new_game(display_name: str, starting_cash: float = DEFAULT_STARTING_CASH, 
                  company_count: int = DEFAULT_COMPANY_COUNT) -> str:
    """MCP 工具：创建新游戏"""
    return new_game(display_name, starting_cash, company_count)


def tool_load_game(game_id: int) -> str:
    """MCP 工具：加载游戏"""
    return load_game(game_id)


def tool_list_games() -> str:
    """MCP 工具：列出所有游戏"""
    return list_games()
