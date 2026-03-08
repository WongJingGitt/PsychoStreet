"""
game_{id}.db 数据库管理
负责单局游戏数据库的创建和连接
"""

import sqlite3
from pathlib import Path
from db.schema import init_game_db


def create_game_db(db_path: str | Path) -> sqlite3.Connection:
    """
    创建新的游戏数据库文件并初始化表结构
    
    Args:
        db_path: 数据库文件路径
    
    Returns:
        sqlite3.Connection: 数据库连接对象
    """
    # 确保目录存在
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 创建数据库连接
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    
    # 启用外键约束
    conn.execute("PRAGMA foreign_keys = ON")
    
    # 设置行工厂
    conn.row_factory = sqlite3.Row
    
    # 初始化表结构
    init_game_db(conn)
    
    return conn


def get_game_conn(db_path: str | Path) -> sqlite3.Connection:
    """
    获取游戏数据库连接（打开已存在的数据库）
    
    Args:
        db_path: 数据库文件路径
    
    Returns:
        sqlite3.Connection: 数据库连接对象
    
    Raises:
        FileNotFoundError: 数据库文件不存在
    """
    db_path = Path(db_path)
    
    if not db_path.exists():
        raise FileNotFoundError(f"游戏数据库不存在: {db_path}")
    
    # 创建连接
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    
    # 启用外键约束
    conn.execute("PRAGMA foreign_keys = ON")
    
    # 设置行工厂
    conn.row_factory = sqlite3.Row
    
    return conn


def init_game_meta(conn: sqlite3.Connection, player_name: str, total_turns: int = 200):
    """
    初始化游戏元数据
    
    Args:
        conn: 数据库连接
        player_name: 玩家名称
        total_turns: 游戏总回合数
    """
    conn.execute(
        "INSERT OR REPLACE INTO GameMeta (key, value) VALUES ('current_turn', '0')"
    )
    conn.execute(
        "INSERT OR REPLACE INTO GameMeta (key, value) VALUES ('total_turns', ?)",
        (str(total_turns),)
    )
    conn.execute(
        "INSERT OR REPLACE INTO GameMeta (key, value) VALUES ('player_name', ?)",
        (player_name,)
    )
    conn.execute(
        "INSERT OR REPLACE INTO GameMeta (key, value) VALUES ('prev_prices', '{}')"
    )
    conn.commit()


def get_current_turn(conn: sqlite3.Connection) -> int:
    """
    获取当前回合数
    
    Args:
        conn: 数据库连接
    
    Returns:
        int: 当前回合数
    """
    cursor = conn.execute("SELECT value FROM GameMeta WHERE key='current_turn'")
    row = cursor.fetchone()
    return int(row["value"]) if row else 0


def increment_turn(conn: sqlite3.Connection) -> int:
    """
    回合数+1并返回新回合数
    
    Args:
        conn: 数据库连接
    
    Returns:
        int: 新的回合数
    """
    current = get_current_turn(conn)
    new_turn = current + 1
    conn.execute(
        "UPDATE GameMeta SET value=? WHERE key='current_turn'",
        (str(new_turn),)
    )
    conn.commit()
    return new_turn


def get_player_name(conn: sqlite3.Connection) -> str:
    """
    获取玩家名称
    
    Args:
        conn: 数据库连接
    
    Returns:
        str: 玩家名称
    """
    cursor = conn.execute("SELECT value FROM GameMeta WHERE key='player_name'")
    row = cursor.fetchone()
    return row["value"] if row else "Unknown"
