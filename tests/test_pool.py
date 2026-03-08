from db.content_pool import get_pool_status, draw_companies
import json

print("=== 池子状态 ===")
print(json.dumps(get_pool_status(), ensure_ascii=False, indent=2))

print("\n=== 抽取5家公司 ===")
companies = draw_companies(5)
for c in companies:
    print(f"  - {c['name']} ({c['industry_tag']})")

print("\n=== 抽取后再查状态 ===")
print(json.dumps(get_pool_status(), ensure_ascii=False, indent=2))
