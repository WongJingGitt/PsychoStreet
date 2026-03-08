import sqlite3
import sys
sys.path.insert(0, ".")

from db.content_pool import get_pool_status, draw_companies, draw_celebrities, draw_institutions

print("=" * 60)
print("【测试1】内容池状态")
print("=" * 60)
status = get_pool_status()
print(f"  公司池: {status['companies_remaining']} 家")
print(f"  名人池: {status['celebrities_remaining']} 人")
print(f"  机构池: {status['institutions_remaining']} 家")

print("\n" + "=" * 60)
print("【测试2】抽取公司（不指定）")
print("=" * 60)
companies = draw_companies(5)
for c in companies:
    print(f"  - {c['name']} ({c['industry_tag']})")

print("\n" + "=" * 60)
print("【测试3】抽取名人")
print("=" * 60)
celebs = draw_celebrities(3)
for c in celebs:
    print(f"  - {c['name']} ({c['role']})")

print("\n" + "=" * 60)
print("【测试4】抽取机构")
print("=" * 60)
insts = draw_institutions(3)
for i in insts:
    print(f"  - {i['name']} ({i['type']})")

print("\n" + "=" * 60)
print("【测试5】行业过滤器")
print("=" * 60)
tech_companies = draw_companies(3, industry_filter="科技")
for c in tech_companies:
    print(f"  - {c['name']} ({c['industry_tag']})")

print("\n" + "=" * 60)
print("【测试6】init_companies 不传参数")
print("=" * 60)

import tools.init_tools as init_tools
import os

os.makedirs("data", exist_ok=True)
conn = sqlite3.connect(":memory:")
conn.row_factory = sqlite3.Row

from db.schema import init_game_db
init_game_db(conn)

result = init_tools.init_companies(conn)
print(result)

print("\n" + "=" * 60)
print("【测试7】检查数据库中的公司")
print("=" * 60)
stocks = conn.execute("SELECT name, industry_tag FROM Stock").fetchall()
for s in stocks:
    print(f"  - {s['name']} ({s['industry_tag']})")

print("\n" + "=" * 60)
print("【测试8】init_institutions")
print("=" * 60)
result = init_tools.init_institutions(conn, count=4)
print(result)

print("\n" + "=" * 60)
print("【测试9】最终池子状态")
print("=" * 60)
status = get_pool_status()
print(f"  公司池: {status['companies_remaining']} 家")
print(f"  名人池: {status['celebrities_remaining']} 人")
print(f"  机构池: {status['institutions_remaining']} 家")

print("\n" + "=" * 60)
print("【全部测试完成】")
print("=" * 60)
