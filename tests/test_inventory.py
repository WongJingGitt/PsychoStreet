import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from db import game_db
from tools import inventory_tools


db_path = "data/games/test_inventory.db"
if os.path.exists(db_path):
    os.remove(db_path)

conn = game_db.create_game_db(db_path)

conn.execute("""
    INSERT INTO Player (id, cash, fame) 
    VALUES (1, 500000, 50)
""")

companies = [
    {"name": "微硬科技", "industry_tag": "科技", "description": "软件巨头"},
    {"name": "谷弟搜索", "industry_tag": "科技", "description": "搜索引擎"},
    {"name": "鸭梨山公司", "industry_tag": "电商", "description": "电商平台"},
]

from tools.init_tools import init_companies, init_market_prices
init_companies(conn, companies)
init_market_prices(conn)

conn.execute("INSERT INTO GameMeta (key, value) VALUES ('current_turn', '1')")
conn.commit()

print("=" * 60)
print("【测试1】获取/购买物品 - 正常购买")
print("=" * 60)
result = inventory_tools.acquire_item(
    conn, "三层豪华游艇", "重资产", "来自摩纳哥二手市场", 300000, 1, "trivial"
)
print(result)
print()

print("=" * 60)
print("【测试2】获取/购买物品 - 现金不足")
print("=" * 60)
result = inventory_tools.acquire_item(
    conn, "私人飞机", "重资产", "湾流G650", 1000000, 1, "easy"
)
print(result)
print()

print("=" * 60)
print("【测试3】查询背包")
print("=" * 60)
items = conn.execute("SELECT * FROM PlayerInventory").fetchall()
for item in items:
    print(f"  ID:{item['item_id']} | {item['name']} | {item['category_tag']} | {item['status']} | ${item['estimated_value']:,}")
print()

print("=" * 60)
print("【测试4】修改物品状态")
print("=" * 60)
result = inventory_tools.update_item_status(conn, 1, "已停泊在公海")
print(result)
print()

print("=" * 60)
print("【测试5】再次查询背包（状态已更新）")
print("=" * 60)
items = conn.execute("SELECT * FROM PlayerInventory").fetchall()
for item in items:
    print(f"  ID:{item['item_id']} | {item['name']} | Status: {item['status']}")
print()

print("=" * 60)
print("【测试6】抵押借款")
print("=" * 60)
result = inventory_tools.take_loan(conn, 1, 150000, 3, 1)
print(result)
print()

print("=" * 60)
print("【测试7】查询背包（已抵押，状态冻结）")
print("=" * 60)
items = conn.execute("SELECT * FROM PlayerInventory").fetchall()
for item in items:
    print(f"  ID:{item['item_id']} | {item['name']} | Status: {item['status']}")
print()

print("=" * 60)
print("【测试8】查询债务")
print("=" * 60)
debts = conn.execute("SELECT * FROM PlayerDebts").fetchall()
for debt in debts:
    print(f"  ID:{debt['debt_id']} | Type:{debt['debt_type']} | Amount:${debt['amount_owed']:,} | Due Turn:{debt['due_turn']}")
print()

print("=" * 60)
print("【测试9】尝试修改已抵押物品状态（应失败）")
print("=" * 60)
result = inventory_tools.update_item_status(conn, 1, "转移至他处")
print(result)
print()

print("=" * 60)
print("【测试10】尝试消耗已抵押物品（应失败）")
print("=" * 60)
result = inventory_tools.consume_item(conn, 1, 100000, "尝试出售")
print(result)
print()

print("=" * 60)
print("【测试11】偿还借款")
print("=" * 60)
result = inventory_tools.repay_loan(conn, 1)
print(result)
print()

print("=" * 60)
print("【测试12】查询背包（抵押已解除）")
print("=" * 60)
items = conn.execute("SELECT * FROM PlayerInventory").fetchall()
for item in items:
    print(f"  ID:{item['item_id']} | {item['name']} | Status: {item['status']}")
print()

print("=" * 60)
print("【测试13】售出物品")
print("=" * 60)
result = inventory_tools.consume_item(conn, 1, 250000, "二手出售")
print(result)
print()

print("=" * 60)
print("【测试14】查询现金（应增加售出款）")
print("=" * 60)
player = conn.execute("SELECT cash FROM Player WHERE id=1").fetchone()
print(f"  当前现金: ${player['cash']:,}")
print()

print("=" * 60)
print("【测试15】获取黑料物品")
print("=" * 60)
result = inventory_tools.acquire_item(
    conn, "某CEO出轨录音带", "致命黑料", "时长30分钟，可信度极高", 50000, 1, "easy"
)
print(result)
print()

print("=" * 60)
print("【测试16】修改黑料状态为藏匿")
print("=" * 60)
item = conn.execute("SELECT item_id FROM PlayerInventory WHERE name='某CEO出轨录音带'").fetchone()
if item:
    result = inventory_tools.update_item_status(conn, item['item_id'], "藏于郊外安全屋")
    print(result)
print()

print("=" * 60)
print("【测试17】查询最终背包状态")
print("=" * 60)
items = conn.execute("SELECT * FROM PlayerInventory").fetchall()
print(f"  背包物品数: {len(items)}")
for item in items:
    print(f"    - {item['name']} ({item['category_tag']}): {item['status']}")
print()

print("=" * 60)
print("【测试18】测试债务逾期清算逻辑")
print("=" * 60)

conn.execute("INSERT INTO PlayerInventory (player_id, name, category_tag, description, estimated_value, status, acquire_turn) VALUES (1, '名画《星空》', '收藏品', '梵高真迹', 500000, '正常持有', 1)")
conn.commit()

item = conn.execute("SELECT item_id FROM PlayerInventory WHERE name='名画《星空》'").fetchone()
loan_item_id = item['item_id']

result = inventory_tools.take_loan(conn, loan_item_id, 200000, 1, 1)
print("  借款1回合:")
print(result)

print("\n  模拟回合推进到第3回合（已逾期）:")
from engines.market_engine import _process_liquidations
traces = _process_liquidations(conn, 3)
print(f"  触发清算次数: {len(traces)}")
for t in traces:
    print(f"    - {t['content']}")

print("\n  检查物品是否被删除:")
item = conn.execute("SELECT * FROM PlayerInventory WHERE item_id=?", (loan_item_id,)).fetchone()
if item:
    print(f"  物品仍存在: {item['name']}")
else:
    print("  物品已被强制删除 ✓")

print("\n  检查债务是否已清除:")
debt = conn.execute("SELECT * FROM PlayerDebts WHERE collateral_item_id=?", (loan_item_id,)).fetchone()
if debt:
    print(f"  债务仍存在: ${debt['amount_owed']:,}")
else:
    print("  债务已清除 ✓")

conn.close()
print("\n" + "=" * 60)
print("【全部测试完成】")
print("=" * 60)
