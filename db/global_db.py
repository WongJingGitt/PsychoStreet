"""
global.db 数据库管理
负责游戏实例的全局索引管理
"""

import sqlite3
from pathlib import Path
from db.schema import init_global_db


# 全局数据库连接（模块级单例）
_global_conn: sqlite3.Connection | None = None
_global_db_path: Path | None = None


def get_global_db_path() -> Path:
    """
    获取 global.db 文件路径
    默认存放在 data/games/ 目录下
    
    Returns:
        Path: global.db 的完整路径
    """
    from pathlib import Path
    
    # 获取项目根目录
    project_root = Path(__file__).parent.parent
    data_dir = project_root / "data" / "games"
    data_dir.mkdir(parents=True, exist_ok=True)
    
    return data_dir / "global.db"


def get_global_conn() -> sqlite3.Connection:
    """
    获取 global.db 的数据库连接（单例模式）
    
    首次调用时会：
    1. 创建 data/games/ 目录
    2. 初始化 global.db 文件
    3. 创建所有必要的表
    
    Returns:
        sqlite3.Connection: global.db 的连接对象
    """
    global _global_conn, _global_db_path
    
    if _global_conn is not None:
        return _global_conn
    
    # 获取数据库路径
    _global_db_path = get_global_db_path()
    
    # 创建数据库连接
    _global_conn = sqlite3.connect(str(_global_db_path), check_same_thread=False)
    
    # 启用外键约束
    _global_conn.execute("PRAGMA foreign_keys = ON")
    
    # 设置行工厂，返回 sqlite3.Row 对象（支持字典式访问）
    _global_conn.row_factory = sqlite3.Row
    
    # 初始化数据库表结构
    init_global_db(_global_conn)
    
    return _global_conn


def close_global_conn():
    """
    关闭 global.db 连接
    通常在程序退出时调用
    """
    global _global_conn
    
    if _global_conn is not None:
        _global_conn.close()
        _global_conn = None


def get_active_game_id() -> int | None:
    """
    获取当前激活的游戏 ID
    
    Returns:
        int | None: 激活的游戏ID，若无则返回 None
    """
    conn = get_global_conn()
    cursor = conn.execute("SELECT value FROM Settings WHERE key='active_game_id'")
    row = cursor.fetchone()
    
    if row and row["value"]:
        return int(row["value"])
    return None


def set_active_game_id(game_id: int | None):
    """
    设置当前激活的游戏 ID
    
    Args:
        game_id: 游戏ID，传 None 表示无激活游戏
    """
    conn = get_global_conn()
    value = str(game_id) if game_id is not None else None
    conn.execute(
        "INSERT OR REPLACE INTO Settings (key, value) VALUES ('active_game_id', ?)",
        (value,)
    )
    conn.commit()


def create_game_session(display_name: str, db_path: str) -> int:
    """
    创建新的游戏会话记录
    
    Args:
        display_name: 游戏显示名称
        db_path: 游戏数据库文件路径
    
    Returns:
        int: 新创建的 game_id
    """
    from datetime import datetime
    
    conn = get_global_conn()
    now = datetime.now().isoformat()
    
    cursor = conn.execute(
        """INSERT INTO GameSessions 
           (display_name, db_path, created_at, last_played_at, turn, status)
           VALUES (?, ?, ?, ?, 0, 'active')""",
        (display_name, db_path, now, now)
    )
    conn.commit()
    
    return cursor.lastrowid


def update_game_session(game_id: int, turn: int):
    """
    更新游戏会话信息（回合数和最后游玩时间）
    
    Args:
        game_id: 游戏ID
        turn: 当前回合数
    """
    from datetime import datetime
    
    conn = get_global_conn()
    now = datetime.now().isoformat()
    
    conn.execute(
        """UPDATE GameSessions 
           SET turn=?, last_played_at=? 
           WHERE game_id=?""",
        (turn, now, game_id)
    )
    conn.commit()


def get_game_session(game_id: int) -> dict | None:
    """
    获取游戏会话信息
    
    Args:
        game_id: 游戏ID
    
    Returns:
        dict | None: 游戏会话信息，若不存在或数据库文件损坏则返回 None
    """
    conn = get_global_conn()
    cursor = conn.execute(
        "SELECT * FROM GameSessions WHERE game_id=?",
        (game_id,)
    )
    row = cursor.fetchone()
    
    if row:
        session = dict(row)
        db_path = session.get("db_path")
        if db_path and Path(db_path).exists():
            return session
    return None


def list_game_sessions() -> list[dict]:
    """
    列出所有游戏会话
    
    Returns:
        list[dict]: 游戏会话列表（已自动过滤掉数据库文件不存在的会话），按最后游玩时间倒序排列
    """
    conn = get_global_conn()
    cursor = conn.execute(
        "SELECT * FROM GameSessions ORDER BY last_played_at DESC"
    )
    sessions = []
    for row in cursor.fetchall():
        session = dict(row)
        db_path = session.get("db_path")
        if db_path and Path(db_path).exists():
            sessions.append(session)
    return sessions
