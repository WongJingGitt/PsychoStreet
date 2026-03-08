"""
数据库迁移脚本：为 V2.0 混沌市场引擎添加新字段
兼容旧存档，自动迁移数据
"""
import sqlite3
from pathlib import Path


MIGRATION_SQL = """
-- Stock 表新增字段
ALTER TABLE Stock ADD COLUMN base_liquidity REAL NOT NULL DEFAULT 1000000.0;
ALTER TABLE Stock ADD COLUMN current_liquidity REAL NOT NULL DEFAULT 1000000.0;
ALTER TABLE Stock ADD COLUMN retail_sentiment REAL NOT NULL DEFAULT 0.0;
ALTER TABLE Stock ADD COLUMN volatility_index REAL NOT NULL DEFAULT 0.0;

-- 如果 hidden_liquidity 存在，将 base_liquidity 初始化为 hidden_liquidity
UPDATE Stock SET base_liquidity = hidden_liquidity, current_liquidity = hidden_liquidity
WHERE hidden_liquidity > 0;
"""


def migrate_game_db(db_path: str) -> bool:
    """
    迁移单个游戏数据库

    Args:
        db_path: 游戏数据库文件路径

    Returns:
        bool: 迁移是否成功
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(Stock)")
        columns = {row[1] for row in cursor.fetchall()}

        if "base_liquidity" not in columns:
            cursor.executescript(MIGRATION_SQL)
            conn.commit()
            print(f"✓ 迁移完成: {db_path}")
        else:
            print(f"- 跳过（已迁移）: {db_path}")

        conn.close()
        return True

    except Exception as e:
        print(f"✗ 迁移失败: {db_path} - {e}")
        return False


def migrate_all_games(games_dir: str = "data/games") -> None:
    """
    迁移所有游戏数据库

    Args:
        games_dir: 游戏文件目录
    """
    games_path = Path(games_dir)
    if not games_path.exists():
        print(f"目录不存在: {games_dir}")
        return

    db_files = list(games_path.glob("game_*.db"))
    print(f"发现 {len(db_files)} 个游戏文件")

    success_count = 0
    for db_file in db_files:
        if migrate_game_db(str(db_file)):
            success_count += 1

    print(f"\n迁移完成: {success_count}/{len(db_files)} 成功")


def create_new_tables(conn: sqlite3.Connection) -> None:
    """
    为现有数据库创建新表（如果不存在）

    Args:
        conn: 数据库连接
    """
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Institution (
            inst_id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name              TEXT    NOT NULL,
            type              TEXT    NOT NULL DEFAULT 'value'
                              CHECK(type IN ('value', 'hedge_short', 'quant')),
            capital           REAL    NOT NULL DEFAULT 10000000.0,
            risk_tolerance    REAL    NOT NULL DEFAULT 0.5,
            status            TEXT    NOT NULL DEFAULT 'active'
                              CHECK(status IN ('active', 'bankrupt'))
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS InstitutionPosition (
            pos_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            inst_id     INTEGER NOT NULL REFERENCES Institution(inst_id),
            stock_id    INTEGER NOT NULL REFERENCES Stock(id),
            position_type TEXT  NOT NULL DEFAULT 'long'
                             CHECK(position_type IN ('long', 'short')),
            volume_usd  REAL    NOT NULL DEFAULT 0.0,
            avg_cost    REAL    NOT NULL DEFAULT 0.0,
            UNIQUE(inst_id, stock_id, position_type)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS MarketTrace (
            trace_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            turn        INTEGER NOT NULL,
            stock_id    INTEGER REFERENCES Stock(id),
            trace_type  TEXT    NOT NULL
                         CHECK(trace_type IN ('broadcast', 'rumor')),
            content     TEXT    NOT NULL
        )
    """)

    cursor.execute("PRAGMA table_info(CompanyNPC)")
    columns = {row[1] for row in cursor.fetchall()}
    if "npc_type" not in columns:
        cursor.execute("ALTER TABLE CompanyNPC ADD COLUMN npc_type TEXT NOT NULL DEFAULT 'executive'")
        cursor.execute("ALTER TABLE CompanyNPC ADD COLUMN influence_power INTEGER NOT NULL DEFAULT 0")

    conn.commit()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        migrate_all_games(sys.argv[1])
    else:
        migrate_all_games()
