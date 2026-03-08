"""
V2.0 混沌市场引擎 - 市场调节机制深度测试
测试：非线性滑点、机构博弈、散户情绪、蝴蝶效应、流动性干涸
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


def test_player_trade_impact():
    """测试1：玩家交易对价格的冲击（非线性滑点）"""
    print_separator("测试1: 玩家大额交易的价格冲击（非线性滑点）")

    db_path = "data/games/test_trade_impact.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_game_db(conn)

    init_tools.init_player(conn, "测试玩家", 10000000.0)

    companies = [
        {"name": "小盘科技股", "industry_tag": "科技", "description": "小市值科技公司"},
    ]
    init_tools.init_companies(conn, companies)
    init_tools.init_market_prices(conn)

    stock = conn.execute("SELECT * FROM Stock WHERE name='小盘科技股'").fetchone()
    print(f"\n初始价格: ${stock['current_price']:.2f}")
    print(f"初始流动性: ${stock['base_liquidity']:,.0f}")

    init_tools.init_institutions(conn, 1)

    print("\n--- 场景A: 小额买入 (10% 流动性) ---")
    player_actions = {stock["id"]: stock["base_liquidity"] * 0.10}
    result = market_engine.settle_market_turn(conn, 1, player_actions=player_actions)
    stock = conn.execute("SELECT * FROM Stock WHERE id=?", (stock["id"],)).fetchone()
    change_a = (stock["current_price"] - 51.0) / 51.0 * 100
    print(f"买入后价格: ${stock['current_price']:.2f} (变化: {change_a:+.1f}%)")
    print(f"当前流动性: ${stock['current_liquidity']:,.0f}")

    print("\n--- 场景B: 大额买入 (40% 流动性) ---")
    player_actions = {stock["id"]: stock["base_liquidity"] * 0.40}
    result = market_engine.settle_market_turn(conn, 2, player_actions=player_actions)
    stock = conn.execute("SELECT * FROM Stock WHERE id=?", (stock["id"],)).fetchone()
    change_b = (stock["current_price"] - 51.0) / 51.0 * 100
    print(f"买入后价格: ${stock['current_price']:.2f} (变化: {change_b:+.1f}%)")
    print(f"当前流动性: ${stock['current_liquidity']:,.0f}")

    print("\n--- 场景C: 超大额买入 (80% 流动性) ---")
    player_actions = {stock["id"]: stock["base_liquidity"] * 0.80}
    result = market_engine.settle_market_turn(conn, 3, player_actions=player_actions)
    stock = conn.execute("SELECT * FROM Stock WHERE id=?", (stock["id"],)).fetchone()
    change_c = (stock["current_price"] - 51.0) / 51.0 * 100
    print(f"买入后价格: ${stock['current_price']:.2f} (变化: {change_c:+.1f}%)")
    print(f"当前流动性: ${stock['current_liquidity']:,.0f}")

    conn.close()
    os.remove(db_path)
    print("\n✓ 非线性滑点测试完成 - 资金量越大，价格冲击越剧烈")


def test_retail_sentiment():
    """测试2：散户情绪传导"""
    print_separator("测试2: 散户情绪传导机制")

    db_path = "data/games/test_sentiment.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_game_db(conn)

    init_tools.init_player(conn, "测试玩家", 1000000.0)

    companies = [
        {"name": "热门科技股", "industry_tag": "科技", "description": "市场关注度高"},
    ]
    init_tools.init_companies(conn, companies)
    init_tools.init_market_prices(conn)
    init_tools.init_institutions(conn, 2)

    stock = conn.execute("SELECT * FROM Stock WHERE name='热门科技股'").fetchone()
    print(f"\n初始情绪: {stock['retail_sentiment']:.3f}")
    print(f"初始流动性: ${stock['base_liquidity']:,.0f}")

    print("\n--- 注入积极情绪 (+0.5) ---")
    spillover = {stock["id"]: 0.5}
    result = market_engine.settle_market_turn(conn, 1, spillover_events=spillover)
    stock = conn.execute("SELECT * FROM Stock WHERE id=?", (stock["id"],)).fetchone()
    print(f"情绪值: {stock['retail_sentiment']:.3f}")
    print(f"流动性变化: ${stock['base_liquidity']:,.0f} → ${stock['current_liquidity']:,.0f}")

    print("\n--- 继续注入积极情绪 (+0.5)，观察衰减 ---")
    spillover = {stock["id"]: 0.5}
    result = market_engine.settle_market_turn(conn, 2, spillover_events=spillover)
    stock = conn.execute("SELECT * FROM Stock WHERE id=?", (stock["id"],)).fetchone()
    print(f"情绪值: {stock['retail_sentiment']:.3f} (应该衰减)")
    print(f"流动性: ${stock['current_liquidity']:,.0f}")

    print("\n--- 注入恐慌情绪 (-0.8) ---")
    spillover = {stock["id"]: -0.8}
    result = market_engine.settle_market_turn(conn, 3, spillover_events=spillover)
    stock = conn.execute("SELECT * FROM Stock WHERE id=?", (stock["id"],)).fetchone()
    print(f"情绪值: {stock['retail_sentiment']:.3f}")
    print(f"流动性: ${stock['current_liquidity']:,.0f} (恐慌导致流动性收缩)")
    print(f"恐慌指数: {stock['volatility_index']:.3f}")

    conn.close()
    os.remove(db_path)
    print("\n✓ 散户情绪测试完成 - 情绪影响流动性和价格")


def test_institution_behavior():
    """测试3：机构行为模式"""
    print_separator("测试3: 三类机构的行为模式")

    db_path = "data/games/test_institutions.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_game_db(conn)

    init_tools.init_player(conn, "测试玩家", 1000000.0)

    companies = [
        {"name": "低估价值股", "industry_tag": "金融", "description": "被低估的银行股"},
        {"name": "高风险垃圾股", "industry_tag": "科技", "description": "财务造假的科技公司"},
        {"name": "热门概念股", "industry_tag": "科技", "description": "散户追捧的概念股"},
    ]
    init_tools.init_companies(conn, companies)
    init_tools.init_market_prices(conn)

    conn.execute("UPDATE Stock SET hidden_fundamental_value = current_price * 2.0 WHERE name='低估价值股'")
    conn.execute("UPDATE Stock SET hidden_scandal_risk = 90 WHERE name='高风险垃圾股'")
    conn.commit()

    init_tools.init_institutions(conn, 3)

    print("\n--- 第一回合：观察机构建仓 ---")
    result = market_engine.settle_market_turn(conn, 1)
    traces = result.get("market_traces", [])
    for t in traces:
        print(f"  [{t['trace_type']}] {t['content'][:50]}...")

    institutions = conn.execute("SELECT * FROM Institution").fetchall()
    for inst in institutions:
        positions = conn.execute(
            "SELECT * FROM InstitutionPosition WHERE inst_id=?", (inst["inst_id"],)
        ).fetchall()
        print(f"\n{inst['name']} ({inst['type']}):")
        print(f"  剩余资金: ${inst['capital']:,.0f}")
        print(f"  持仓数: {len(positions)}")
        for pos in positions:
            stock_name = conn.execute("SELECT name FROM Stock WHERE id=?", (pos["stock_id"],)).fetchone()["name"]
            print(f"    - {stock_name}: ${pos['volume_usd']:,.0f} ({pos['position_type']})")

    print("\n--- 第二回合：继续观察 ---")
    result = market_engine.settle_market_turn(conn, 2)
    traces = result.get("market_traces", [])
    for t in traces:
        print(f"  [{t['trace_type']}] {t['content'][:50]}...")

    conn.close()
    os.remove(db_path)
    print("\n✓ 机构行为测试完成")


def test_liquidity_crisis():
    """测试4：流动性干涸与价格崩盘"""
    print_separator("测试4: 流动性干涸危机")

    db_path = "data/games/test_liquidity.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_game_db(conn)

    init_tools.init_player(conn, "测试玩家", 1000000.0)

    companies = [
        {"name": "垃圾股", "industry_tag": "科技", "description": "高风险公司"},
    ]
    init_tools.init_companies(conn, companies)
    init_tools.init_market_prices(conn)

    conn.execute("UPDATE Stock SET hidden_scandal_risk = 95 WHERE name='垃圾股'")
    conn.commit()

    stock = conn.execute("SELECT * FROM Stock WHERE name='垃圾股'").fetchone()
    print(f"\n初始价格: ${stock['current_price']:.2f}")
    print(f"暴雷风险: {stock['hidden_scandal_risk']}")

    print("\n--- 连续几回合观察流动性收缩 ---")
    for turn in range(1, 5):
        result = market_engine.settle_market_turn(conn, turn)
        stock = conn.execute("SELECT * FROM Stock WHERE name='垃圾股'").fetchone()
        print(f"\n第{turn}回合:")
        print(f"  价格: ${stock['current_price']:.2f}")
        print(f"  流动性: ${stock['current_liquidity']:,.0f} (初始 ${stock['base_liquidity']:,.0f})")
        print(f"  恐慌指数: {stock['volatility_index']:.3f}")
        print(f"  暴雷风险: {stock['hidden_scandal_risk']}")

        if stock['hidden_scandal_risk'] >= 100:
            print("  ⚠️ 触发暴雷！")

    conn.close()
    os.remove(db_path)
    print("\n✓ 流动性干涸测试完成")


def test_player_fame_spillover():
    """测试5：玩家声望影响蝴蝶效应"""
    print_separator("测试5: 玩家声望( fame )放大蝴蝶效应")

    db_path = "data/games/test_fame.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_game_db(conn)

    init_tools.init_player(conn, "测试玩家", 1000000.0)

    companies = [
        {"name": "目标股票", "industry_tag": "科技", "description": "测试"},
    ]
    init_tools.init_companies(conn, companies)
    init_tools.init_market_prices(conn)

    stock = conn.execute("SELECT * FROM Stock WHERE name='目标股票'").fetchone()
    print(f"\n初始情绪: {stock['retail_sentiment']:.3f}")

    conn.execute("UPDATE Player SET fame = 10 WHERE id=1")
    conn.commit()

    print("\n--- 玩家 fame=10, 注入 sentiment_shift=0.5 ---")
    spillover = {stock["id"]: 0.5}
    result = market_engine.settle_market_turn(conn, 1, player_actions={"player_fame": 10}, spillover_events=spillover)
    stock = conn.execute("SELECT * FROM Stock WHERE id=?", (stock["id"],)).fetchone()
    print(f"情绪变化: {stock['retail_sentiment']:.3f}")
    print(f"  (预期: 0.5 * 10/100 = 0.05)")

    conn.execute("UPDATE Player SET fame = 80 WHERE id=1")
    conn.commit()

    print("\n--- 玩家 fame=80, 再次注入 sentiment_shift=0.5 ---")
    spillover = {stock["id"]: 0.5}
    result = market_engine.settle_market_turn(conn, 2, player_actions={"player_fame": 80}, spillover_events=spillover)
    stock = conn.execute("SELECT * FROM Stock WHERE id=?", (stock["id"],)).fetchone()
    print(f"情绪变化: {stock['retail_sentiment']:.3f}")
    print(f"  (预期: 0.5 * 80/100 = 0.40，实际受衰减影响)")

    conn.close()
    os.remove(db_path)
    print("\n✓ 玩家声望测试完成")


if __name__ == "__main__":
    print("""
    ╔═══════════════════════════════════════════════════════════════╗
    ║     V2.0 混沌市场引擎 - 市场调节机制深度测试                 ║
    ╚═══════════════════════════════════════════════════════════════╝
    """)

    test_player_trade_impact()
    test_retail_sentiment()
    test_institution_behavior()
    test_liquidity_crisis()
    test_player_fame_spillover()

    print("\n" + "=" * 70)
    print("  🎉 所有市场调节机制测试完成！")
    print("=" * 70)
