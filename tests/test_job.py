import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from db import game_db
from tools import job_tools

db_path = "data/games/test_job.db"
if os.path.exists(db_path):
    os.remove(db_path)

conn = game_db.create_game_db(db_path)

conn.execute("""
    INSERT INTO Player (id, cash, fame) 
    VALUES (1, 100000, 0)
""")

companies = [
    {"name": "微硬科技", "industry_tag": "科技", "description": "软件巨头"},
    {"name": "谷弟搜索", "industry_tag": "科技", "description": "搜索引擎"},
    {"name": "鸭梨山公司", "industry_tag": "电商", "description": "电商平台"},
]

from tools.init_tools import init_companies, init_market_prices
init_companies(conn, companies)
init_market_prices(conn)

print("=== 测试1: 申请入职 ===")
result = job_tools.apply_job(conn, company_id=1, position_level="entry")
print(result)

print("\n=== 测试2: 查询工作状态 ===")
result = job_tools.get_job_info(conn)
print(result)

print("\n=== 测试3: 再次申请（已有工作）===")
result = job_tools.apply_job(conn, company_id=2, position_level="entry")
print(result)

print("\n=== 测试4: 离职 ===")
result = job_tools.quit_job(conn)
print(result)

print("\n=== 测试5: 离职后查询 ===")
result = job_tools.get_job_info(conn)
print(result)

print("\n=== 测试6: 再次申请基层职位（ fame=0 应该成功率高）===")
result = job_tools.apply_job(conn, company_id=2, position_level="entry")
print(result)

print("\n=== 测试7: 先离职 ===")
result = job_tools.quit_job(conn)
print(result)

print("\n=== 测试8: 申请中层职位（ fame=0 应该失败）===")
result = job_tools.apply_job(conn, company_id=3, position_level="middle")
print(result)

conn.close()
print("\n测试完成！")
