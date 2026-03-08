"""
数据库迁移脚本：为 Stock 表添加退市和 IPO 相关字段

使用方法：
python migrate_add_ipo_fields.py

说明：
- 为所有已存在的游戏数据库添加以下字段：
  - is_delisted: 是否已退市
  - delisting_risk: 退市风险值
  - consecutive_decline_turns: 连续下跌回合数
  - last_turn_price: 上回合价格
  - listed_turn: 上市回合
- 如果字段已存在则跳过
"""

import sqlite3
from pathlib import Path


def migrate_game_db(db_path: Path):
    """为单个游戏数据库添加 IPO 相关字段"""
    print(f"正在迁移: {db_path}")
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    try:
        # 检查字段是否已存在
        cursor = conn.execute("PRAGMA table_info(Stock)")
        columns = [row[1] for row in cursor.fetchall()]
        
        fields_to_add = {
            "is_delisted": "INTEGER NOT NULL DEFAULT 0",
            "delisting_risk": "INTEGER NOT NULL DEFAULT 0",
            "consecutive_decline_turns": "INTEGER NOT NULL DEFAULT 0",
            "last_turn_price": "REAL NOT NULL DEFAULT 0.0",
            "listed_turn": "INTEGER NOT NULL DEFAULT 0",
        }
        
        added_count = 0
        for field_name, field_def in fields_to_add.items():
            if field_name not in columns:
                conn.execute(f"ALTER TABLE Stock ADD COLUMN {field_name} {field_def}")
                added_count += 1
                print(f"  ✓ 已添加字段: {field_name}")
            else:
                print(f"  - 字段已存在: {field_name}")
        
        if added_count > 0:
            # 初始化 last_turn_price 为当前价格
            conn.execute(
                "UPDATE Stock SET last_turn_price = current_price WHERE last_turn_price = 0.0"
            )
            conn.commit()
            print(f"  ✓ 已初始化 last_turn_price")
        else:
            print(f"  ✓ 所有字段已存在，无需迁移")
        
    except Exception as e:
        print(f"  ✗ 迁移失败: {e}")
    
    finally:
        conn.close()


def main():
    """扫描并迁移所有游戏数据库"""
    # 游戏数据库存储路径
    data_dir = Path(__file__).parent / "data"
    
    if not data_dir.exists():
        print("data 目录不存在，无需迁移")
        return
    
    # 查找所有 game_*.db 文件
    game_dbs = list(data_dir.glob("game_*.db"))
    
    if not game_dbs:
        print("未找到任何游戏数据库")
        return
    
    print(f"找到 {len(game_dbs)} 个游戏数据库\n")
    
    for db_path in game_dbs:
        migrate_game_db(db_path)
        print()
    
    print(f"迁移完成！")


if __name__ == "__main__":
    main()
