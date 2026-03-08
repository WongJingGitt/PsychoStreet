"""
V2.0 三类AI机构深度测试
测试：Value基金、Short对冲基金、Quant量化基金的独立决策与博弈
"""
import sqlite3
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db.schema import init_game_db
from tools import init_tools
from engines import market_engine
import json


def print_separator(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def test_value_fund():
    """测试1：Value基金 - 价值发现与止损"""
    print_separator("测试1: Value基金的价值发现与止损机制")

    db_path = "data/games/test_value_fund.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_game_db(conn)

    init_tools.init_player(conn, "测试玩家", 1000000.0)

    companies = [
        {"name": "严重低估股", "industry_tag": "金融", "description": "内在价值被严重低估"},
        {"name": "正常价格股", "industry_tag": "科技", "description": "价格合理"},
    ]
    init_tools.init_companies(conn, companies)
    init_tools.init_market_prices(conn)

    stock_undervalued = conn.execute("SELECT * FROM Stock WHERE name='严重低估股'").fetchone()
    stock_normal = conn.execute("SELECT * FROM Stock WHERE name='正常价格股'").fetchone()

    fundamental = stock_undervalued["current_price"] * 2.5
    conn.execute(
        "UPDATE Stock SET hidden_fundamental_value=? WHERE name='严重低估股'",
        (fundamental,)
    )
    conn.commit()

    print(f"\n初始价格: ${stock_undervalued['current_price']:.2f}")
    print(f"内在价值: ${fundamental:.2f} (低估 {((fundamental/stock_undervalued['current_price'])-1)*100:.0f}%)")

    result = init_tools.init_institutions(conn, 1, types=["value"])
    print(f"\n{result}")

    print("\n--- 第1回合：观察Value基金建仓 ---")
    result = market_engine.settle_market_turn(conn, 1)

    inst = conn.execute("SELECT * FROM Institution WHERE type='value'").fetchone()
    print(f"\n{inst['name']} (Value基金):")
    print(f"  初始资金: $200,000,000")
    print(f"  当前资金: ${inst['capital']:,.0f}")

    positions = conn.execute(
        "SELECT * FROM InstitutionPosition WHERE inst_id=? AND position_type='long'",
        (inst["inst_id"],)
    ).fetchall()
    for pos in positions:
        stock_name = conn.execute("SELECT name FROM Stock WHERE id=?", (pos["stock_id"],)).fetchone()["name"]
        print(f"  持仓: {stock_name} - ${pos['volume_usd']:,.0f}")

    traces = result.get("market_traces", [])
    print("\n市场痕迹:")
    for t in traces:
        print(f"  [{t['trace_type']}] {t['content'][:60]}...")

    conn.close()
    os.remove(db_path)
    print("\n✓ Value基金测试完成")


def test_short_fund():
    """测试2：Short对冲基金 - 做空与暴雷"""
    print_separator("测试2: Short对冲基金的做空与暴雷机制")

    db_path = "data/games/test_short_fund.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_game_db(conn)

    init_tools.init_player(conn, "测试玩家", 1000000.0)

    companies = [
        {"name": "高风险垃圾股", "industry_tag": "科技", "description": "财务造假嫌疑"},
    ]
    init_tools.init_companies(conn, companies)
    init_tools.init_market_prices(conn)

    conn.execute("UPDATE Stock SET hidden_scandal_risk = 85 WHERE name='高风险垃圾股'")
    conn.commit()

    stock = conn.execute("SELECT * FROM Stock WHERE name='高风险垃圾股'").fetchone()
    print(f"\n初始暴雷风险: {stock['hidden_scandal_risk']}")
    print(f"做空阈值: >80")

    result = init_tools.init_institutions(conn, 1, types=["hedge_short"])
    print(f"\n{result}")

    print("\n--- 第1回合：观察Short基金建仓 ---")
    result = market_engine.settle_market_turn(conn, 1)

    inst = conn.execute("SELECT * FROM Institution WHERE type='hedge_short'").fetchone()
    print(f"\n{inst['name']} (Short基金):")
    print(f"  初始资金: $200,000,000")
    print(f"  当前资金: ${inst['capital']:,.0f}")

    positions = conn.execute(
        "SELECT * FROM InstitutionPosition WHERE inst_id=? AND position_type='short'",
        (inst["inst_id"],)
    ).fetchall()
    for pos in positions:
        stock_name = conn.execute("SELECT name FROM Stock WHERE id=?", (pos["stock_id"],)).fetchone()["name"]
        print(f"  空头: {stock_name} - ${pos['volume_usd']:,.0f}")

    traces = result.get("market_traces", [])
    print("\n市场痕迹:")
    for t in traces:
        print(f"  [{t['trace_type']}] {t['content'][:60]}...")

    print("\n--- 第2回合：观察是否会发布做空报告 ---")
    result = market_engine.settle_market_turn(conn, 2)

    stock = conn.execute("SELECT * FROM Stock WHERE name='高风险垃圾股'").fetchone()
    print(f"\n股票情绪: {stock['retail_sentiment']:.2f} (应该大幅下降)")

    traces = result.get("market_traces", [])
    print("\n市场痕迹:")
    for t in traces:
        print(f"  [{t['trace_type']}] {t['content'][:60]}...")

    conn.close()
    os.remove(db_path)
    print("\n✓ Short基金测试完成")


def test_quant_fund():
    """测试3：Quant量化基金 - 追涨杀跌"""
    print_separator("测试3: Quant量化基金的追涨杀跌机制")

    db_path = "data/games/test_quant_fund.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_game_db(conn)

    init_tools.init_player(conn, "测试玩家", 1000000.0)

    companies = [
        {"name": "热门概念股", "industry_tag": "科技", "description": "散户追捧"},
    ]
    init_tools.init_companies(conn, companies)
    init_tools.init_market_prices(conn)

    stock = conn.execute("SELECT * FROM Stock WHERE name='热门概念股'").fetchone()
    print(f"\n初始情绪: {stock['retail_sentiment']}")

    result = init_tools.init_institutions(conn, 1, types=["quant"])
    print(f"\n{result}")

    print("\n--- 第1回合：注入正向情绪 +0.5 ---")
    spillover = {stock["id"]: 0.5}
    result = market_engine.settle_market_turn(conn, 1, spillover_events=spillover)

    stock = conn.execute("SELECT * FROM Stock WHERE name='热门概念股'").fetchone()
    print(f"情绪: {stock['retail_sentiment']:.2f} (>0.3阈值)")

    inst = conn.execute("SELECT * FROM Institution WHERE type='quant'").fetchone()
    print(f"\n{inst['name']} (Quant基金):")
    positions = conn.execute(
        "SELECT * FROM InstitutionPosition WHERE inst_id=? AND position_type='long'",
        (inst["inst_id"],)
    ).fetchall()
    if positions:
        for pos in positions:
            stock_name = conn.execute("SELECT name FROM Stock WHERE id=?", (pos["stock_id"],)).fetchone()["name"]
            print(f"  多头: {stock_name} - ${pos['volume_usd']:,.0f}")
    else:
        print(f"  未建仓 (可能资金不足)")

    print("\n--- 第2回合：注入负向情绪 -0.5 ---")
    spillover = {stock["id"]: -0.5}
    result = market_engine.settle_market_turn(conn, 2, spillover_events=spillover)

    stock = conn.execute("SELECT * FROM Stock WHERE name='热门概念股'").fetchone()
    print(f"情绪: {stock['retail_sentiment']:.2f} (<-0.3阈值)")

    positions = conn.execute(
        "SELECT * FROM InstitutionPosition WHERE inst_id=?",
        (inst["inst_id"],)
    ).fetchall()
    print(f"\n当前持仓数: {len(positions)}")
    for pos in positions:
        stock_name = conn.execute("SELECT name FROM Stock WHERE id=?", (pos["stock_id"],)).fetchone()["name"]
        print(f"  {pos['position_type']}: {stock_name} - ${pos['volume_usd']:,.0f}")

    conn.close()
    os.remove(db_path)
    print("\n✓ Quant基金测试完成")


def test_institution_bankruptcy():
    """测试4：机构破产与强制清算"""
    print_separator("测试4: 机构破产与强制清算")

    db_path = "data/games/test_inst_bankruptcy.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_game_db(conn)

    init_tools.init_player(conn, "测试玩家", 1000000.0)

    companies = [
        {"name": "暴跌股", "industry_tag": "科技", "description": "即将暴跌"},
    ]
    init_tools.init_companies(conn, companies)
    init_tools.init_market_prices(conn)

    result = init_tools.init_institutions(conn, 1, types=["value"])
    print(f"\n{result}")

    inst = conn.execute("SELECT * FROM Institution WHERE type='value'").fetchone()
    print(f"\n初始资金: ${inst['capital']:,.0f}")

    stock = conn.execute("SELECT * FROM Stock WHERE name='暴跌股'").fetchone()

    conn.execute(
        "INSERT INTO InstitutionPosition (inst_id, stock_id, position_type, volume_usd, avg_cost) VALUES (?, ?, 'long', ?, ?)",
        (inst["inst_id"], stock["id"], 50000000, stock["current_price"])
    )
    conn.commit()
    print(f"已手动注入持仓: $50,000,000 (成本: ${stock['current_price']:.2f})")

    print("\n--- 制造暴跌场景: 内在价值设为1元 (暴跌99%) ---")
    conn.execute(
        "UPDATE Stock SET hidden_fundamental_value = 1.0 WHERE name='暴跌股'",
    )
    conn.commit()

    print("\n--- 第1回合：触发止损 ---")
    result = market_engine.settle_market_turn(conn, 1)

    inst = conn.execute("SELECT * FROM Institution WHERE type='value'").fetchone()
    print(f"\n机构状态:")
    print(f"  资金: ${inst['capital']:,.0f}")
    print(f"  状态: {inst['status']}")

    traces = result.get("market_traces", [])
    print("\n市场痕迹:")
    for t in traces:
        print(f"  [{t['trace_type']}] {t['content'][:60]}...")

    conn.close()
    os.remove(db_path)
    print("\n✓ 机构破产测试完成")


def test_all_three_institutions():
    """测试5：三方机构博弈"""
    print_separator("测试5: 三方机构同台博弈")

    db_path = "data/games/test_three_way.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_game_db(conn)

    init_tools.init_player(conn, "测试玩家", 1000000.0)

    companies = [
        {"name": "潜力股", "industry_tag": "科技", "description": "低估+高风险"},
        {"name": "垃圾股", "industry_tag": "地产", "description": "暴雷股"},
    ]
    init_tools.init_companies(conn, companies)
    init_tools.init_market_prices(conn)

    stock_potential = conn.execute("SELECT * FROM Stock WHERE name='潜力股'").fetchone()
    stock_junk = conn.execute("SELECT * FROM Stock WHERE name='垃圾股'").fetchone()

    conn.execute("UPDATE Stock SET hidden_fundamental_value=? WHERE id=?", 
                 (stock_potential["current_price"] * 2.0, stock_potential["id"]))
    conn.execute("UPDATE Stock SET hidden_scandal_risk=90 WHERE id=?", 
                 (stock_junk["id"],))
    conn.commit()

    result = init_tools.init_institutions(conn, 3)
    print(f"\n{result}")

    print("\n--- 10回合博弈观察 ---")
    for turn in range(1, 11):
        result = market_engine.settle_market_turn(conn, turn)

        print(f"\n=== 第{turn}回合 ===")

        institutions = conn.execute("SELECT * FROM Institution WHERE status='active'").fetchall()
        print(f"活跃机构数: {len(institutions)}")
        for inst in institutions:
            positions = conn.execute("SELECT COUNT(*) as cnt FROM InstitutionPosition WHERE inst_id=?", 
                                    (inst["inst_id"],)).fetchone()["cnt"]
            print(f"  {inst['name']} ({inst['type']}): ${inst['capital']:,.0f}, {positions}个持仓")

        stock_potential = conn.execute("SELECT * FROM Stock WHERE name='潜力股'").fetchone()
        stock_junk = conn.execute("SELECT * FROM Stock WHERE name='垃圾股'").fetchone()
        print(f"潜力股: ${stock_potential['current_price']:.2f}, 情绪:{stock_potential['retail_sentiment']:.2f}")
        print(f"垃圾股: ${stock_junk['current_price']:.2f}, 风险:{stock_junk['hidden_scandal_risk']}")

        if turn == 1:
            traces = result.get("market_traces", [])
            if traces:
                print("市场痕迹:")
                for t in traces[:3]:
                    print(f"  [{t['trace_type']}] {t['content'][:50]}...")

    institutions = conn.execute("SELECT * FROM Institution").fetchall()
    print("\n=== 最终状态 ===")
    for inst in institutions:
        print(f"{inst['name']} ({inst['type']}): 状态={inst['status']}, 资金=${inst['capital']:,.0f}")

    conn.close()
    os.remove(db_path)
    print("\n✓ 三方博弈测试完成")


if __name__ == "__main__":
    print("""
    ╔═══════════════════════════════════════════════════════════════╗
    ║          V2.0 三类AI机构深度测试                               ║
    ╚═══════════════════════════════════════════════════════════════╝
    """)

    test_value_fund()
    test_short_fund()
    test_quant_fund()
    test_institution_bankruptcy()
    test_all_three_institutions()

    print("\n" + "=" * 70)
    print("  🎉 所有机构测试完成！")
    print("=" * 70)
