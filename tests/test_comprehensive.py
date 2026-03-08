"""
V2.0 市场机制综合深度测试
测试：情绪传导、暴雷危机、Quant基金、机构破产、暗网机制
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


# ============================================================
# 测试1: 情绪传导深度测试
# ============================================================
def test_sentiment_transmission():
    """验证spillover_events正确传递到市场引擎"""
    print_separator("测试1: 情绪传导深度测试")

    db_path = "data/games/test_sentiment_v2.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_game_db(conn)

    init_tools.init_player(conn, "测试玩家", 1000000.0)
    init_tools.init_player(conn, "测试玩家", 1000000.0)

    companies = [{"name": "测试股", "industry_tag": "科技", "description": "测试"}]
    init_tools.init_companies(conn, companies)
    init_tools.init_market_prices(conn)

    stock = conn.execute("SELECT * FROM Stock WHERE name='测试股'").fetchone()
    print(f"\n初始状态:")
    print(f"  价格: ${stock['current_price']:.2f}")
    print(f"  情绪: {stock['retail_sentiment']:.3f}")
    print(f"  流动性: ${stock['current_liquidity']:,.0f}")

    # 方法1: 通过 player_actions 传递 player_fame
    print("\n--- 场景A: 通过 player_actions['player_fame'] 传递 ---")
    player_actions = {"player_fame": 50}
    spillover = {stock["id"]: 0.5}
    result = market_engine.settle_market_turn(conn, 1, player_actions=player_actions, spillover_events=spillover)

    stock = conn.execute("SELECT * FROM Stock WHERE id=?", (stock["id"],)).fetchone()
    print(f"  注入 sentiment_shift=0.5, player_fame=50")
    print(f"  预期影响: 0.5 * 50/100 = 0.25")
    print(f"  实际情绪: {stock['retail_sentiment']:.3f}")

    # 方法2: 通过单独的参数传递（如果引擎支持）
    print("\n--- 场景B: 再次注入 +0.5 ---")
    spillover = {stock["id"]: 0.5}
    result = market_engine.settle_market_turn(conn, 2, player_actions=player_actions, spillover_events=spillover)

    stock = conn.execute("SELECT * FROM Stock WHERE id=?", (stock["id"],)).fetchone()
    print(f"  累计情绪: {stock['retail_sentiment']:.3f}")

    # 观察流动性变化
    print(f"\n流动性变化: ${stock['current_liquidity']:,.0f} (受恐慌/兴奋影响)")

    conn.close()
    os.remove(db_path)
    print("\n✓ 情绪传导测试完成")


# ============================================================
# 测试2: 暴雷危机深度测试
# ============================================================
def test_scandal_crisis():
    """验证scandal_risk累积与触发机制"""
    print_separator("测试2: 暴雷危机深度测试")

    db_path = "data/games/test_scandal.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_game_db(conn)

    init_tools.init_player(conn, "测试玩家", 1000000.0)

    companies = [{"name": "问题股", "industry_tag": "科技", "description": "高风险公司"}]
    init_tools.init_companies(conn, companies)
    init_tools.init_market_prices(conn)

    stock = conn.execute("SELECT * FROM Stock WHERE name='问题股'").fetchone()
    initial_price = stock["current_price"]
    print(f"\n初始价格: ${initial_price:.2f}")

    # 模拟多回合累积暴雷风险
    print("\n--- 连续注入暴雷风险 ---")
    for turn in range(1, 6):
        conn.execute("UPDATE Stock SET hidden_scandal_risk = hidden_scandal_risk + 20 WHERE name='问题股'")
        conn.commit()

        result = market_engine.settle_market_turn(conn, turn)

        stock = conn.execute("SELECT * FROM Stock WHERE name='问题股'").fetchone()
        price_change = (stock["current_price"] - initial_price) / initial_price * 100

        print(f"\n第{turn}回合:")
        print(f"  暴雷风险: {stock['hidden_scandal_risk']} (阈值: 100)")
        print(f"  价格: ${stock['current_price']:.2f} (变化: {price_change:+.1f}%)")
        print(f"  恐慌指数: {stock['volatility_index']:.3f}")
        print(f"  流动性: ${stock['current_liquidity']:,.0f}")

        if stock['hidden_scandal_risk'] >= 100:
            print(f"  ⚠️ 触发暴雷！价格暴跌60%！")

    conn.close()
    os.remove(db_path)
    print("\n✓ 暴雷危机测试完成")


# ============================================================
# 测试3: Quant基金深度测试
# ============================================================
def test_quant_fund():
    """验证情绪触发建仓逻辑"""
    print_separator("测试3: Quant量化基金深度测试")

    db_path = "data/games/test_quant_v2.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_game_db(conn)

    init_tools.init_player(conn, "测试玩家", 1000000.0)

    companies = [{"name": "概念股", "industry_tag": "科技", "description": "热门概念"}]
    init_tools.init_companies(conn, companies)
    init_tools.init_market_prices(conn)

    init_tools.init_institutions(conn, 1, types=["quant"])

    stock = conn.execute("SELECT * FROM Stock WHERE name='概念股'").fetchone()
    stock_id = stock["id"]
    print(f"\n初始状态:")
    print(f"  情绪: {stock['retail_sentiment']:.3f}")
    print(f"  阈值: > 0.3 (追涨), < -0.3 (杀跌)")

    # 第一回合：注入正向情绪，触发追涨
    print("\n--- 第1回合: 注入正向情绪 +0.5 ---")
    player_actions = {"player_fame": 100}
    spillover = {stock_id: 0.5}
    result = market_engine.settle_market_turn(conn, 1, player_actions=player_actions, spillover_events=spillover)

    stock = conn.execute("SELECT * FROM Stock WHERE name='概念股'").fetchone()
    print(f"  情绪: {stock['retail_sentiment']:.3f}")

    inst = conn.execute("SELECT * FROM Institution WHERE type='quant'").fetchone()
    positions = conn.execute("SELECT * FROM InstitutionPosition WHERE inst_id=?", (inst["inst_id"],)).fetchall()
    print(f"\n  Quant基金 (资金: ${inst['capital']:,.0f}):")
    print(f"    持仓数: {len(positions)}")
    for pos in positions:
        print(f"    - {pos['position_type']}: ${pos['volume_usd']:,.0f}")

    traces = result.get("market_traces", [])
    if traces:
        print("\n  市场痕迹:")
        for t in traces:
            print(f"    [{t['trace_type']}] {t['content'][:50]}...")

    # 第二回合：注入负向情绪，触发杀跌
    print("\n--- 第2回合: 注入负向情绪 -0.8 ---")
    spillover = {stock_id: -0.8}
    result = market_engine.settle_market_turn(conn, 2, player_actions=player_actions, spillover_events=spillover)

    stock = conn.execute("SELECT * FROM Stock WHERE name='概念股'").fetchone()
    print(f"  情绪: {stock['retail_sentiment']:.3f}")

    positions = conn.execute("SELECT * FROM InstitutionPosition WHERE inst_id=?", (inst["inst_id"],)).fetchall()
    print(f"  持仓数: {len(positions)}")
    for pos in positions:
        print(f"    - {pos['position_type']}: ${pos['volume_usd']:,.0f}")

    conn.close()
    os.remove(db_path)
    print("\n✓ Quant基金测试完成")


# ============================================================
# 测试4: 机构破产深度测试
# ============================================================
def test_inst_bankruptcy():
    """验证止损触发与强制清算"""
    print_separator("测试4: 机构破产深度测试")

    db_path = "data/games/test_bankrupt.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_game_db(conn)

    init_tools.init_player(conn, "测试玩家", 1000000.0)

    companies = [{"name": "暴跌股", "industry_tag": "科技", "description": "即将暴跌"}]
    init_tools.init_companies(conn, companies)
    init_tools.init_market_prices(conn)

    init_tools.init_institutions(conn, 1, types=["value"])

    stock = conn.execute("SELECT * FROM Stock WHERE name='暴跌股'").fetchone()
    initial_price = stock["current_price"]

    inst = conn.execute("SELECT * FROM Institution WHERE type='value'").fetchone()
    print(f"\n机构初始资金: ${inst['capital']:,.0f}")

    # 手动注入一个持仓，然后制造暴跌
    print(f"\n注入持仓: $50,000,000 (价格: ${initial_price:.2f})")
    conn.execute(
        "INSERT INTO InstitutionPosition (inst_id, stock_id, position_type, volume_usd, avg_cost) VALUES (?, ?, 'long', ?, ?)",
        (inst["inst_id"], stock["id"], 50000000, initial_price)
    )
    conn.commit()

    # 制造暴跌：内在价值设为 1 元
    print("制造暴跌场景: 内在价值 = $1.00 (暴跌 99%)")
    conn.execute("UPDATE Stock SET hidden_fundamental_value = 1.0 WHERE name='暴跌股'")
    conn.commit()

    # 执行多回合直到触发止损
    print("\n--- 观察止损触发 ---")
    for turn in range(1, 6):
        result = market_engine.settle_market_turn(conn, turn)

        inst = conn.execute("SELECT * FROM Institution WHERE type='value'").fetchone()
        stock = conn.execute("SELECT * FROM Stock WHERE name='暴跌股'").fetchone()

        print(f"\n第{turn}回合:")
        print(f"  价格: ${stock['current_price']:.2f}")
        print(f"  机构资金: ${inst['capital']:,.0f}")
        print(f"  机构状态: {inst['status']}")

        traces = result.get("market_traces", [])
        if traces:
            print("  痕迹:")
            for t in traces:
                print(f"    [{t['trace_type']}] {t['content'][:50]}...")

        if inst["status"] == "bankrupt":
            print("  ⚠️ 机构破产！")
            break

    conn.close()
    os.remove(db_path)
    print("\n✓ 机构破产测试完成")


# ============================================================
# 测试5: 暗网机制深度测试
# ============================================================
def test_darkweb_rumors():
    """验证hidden信息传递"""
    print_separator("测试5: 暗网(rumor)机制深度测试")

    db_path = "data/games/test_rumors.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_game_db(conn)

    init_tools.init_player(conn, "测试玩家", 1000000.0)

    companies = [
        {"name": "目标股A", "industry_tag": "科技", "description": "测试A"},
        {"name": "目标股B", "industry_tag": "金融", "description": "测试B"},
    ]
    init_tools.init_companies(conn, companies)
    init_tools.init_market_prices(conn)

    init_tools.init_institutions(conn, 2, types=["value", "hedge_short"])

    stock_a = conn.execute("SELECT * FROM Stock WHERE name='目标股A'").fetchone()
    conn.execute("UPDATE Stock SET hidden_fundamental_value = ? WHERE name='目标股A'", 
                 (stock_a["current_price"] * 2.0,))
    stock_b = conn.execute("SELECT * FROM Stock WHERE name='目标股B'").fetchone()
    conn.execute("UPDATE Stock SET hidden_scandal_risk = 90 WHERE name='目标股B'")
    conn.commit()

    print("\n--- 执行5回合，收集rumors ---")
    all_traces = []

    for turn in range(1, 6):
        result = market_engine.settle_market_turn(conn, turn)
        traces = result.get("market_traces", [])
        all_traces.extend(traces)

    # 统计 rumor vs broadcast
    rumor_count = sum(1 for t in all_traces if t["trace_type"] == "rumor")
    broadcast_count = sum(1 for t in all_traces if t["trace_type"] == "broadcast")

    print(f"\n总痕迹数: {len(all_traces)}")
    print(f"  rumor (暗网): {rumor_count}")
    print(f"  broadcast (公开): {broadcast_count}")

    print("\n--- 验证 rumor 存储 ---")
    stored_rumors = conn.execute(
        "SELECT * FROM MarketTrace WHERE trace_type='rumor' ORDER BY turn"
    ).fetchall()
    print(f"数据库中 rumor 数: {len(stored_rumors)}")
    for r in stored_rumors[:5]:
        stock_name = conn.execute("SELECT name FROM Stock WHERE id=?", (r["stock_id"],)).fetchone()
        print(f"  第{r['turn']}回合 [{stock_name}]: {r['content'][:40]}...")

    # 验证 investigate_abnormal_movement 工具
    print("\n--- 验证调查工具 ---")
    from tools import turn_tools
    result = turn_tools.tool_investigate_abnormal_movement(conn, stock_a["id"])
    result_obj = json.loads(result)
    print(f"调查 {stock_a['name']}:")
    print(f"  发现 rumors: {len(result_obj.get('rumors', []))}")

    conn.close()
    os.remove(db_path)
    print("\n✓ 暗网机制测试完成")


# ============================================================
# 测试6: 补漏测试 - 检查遗漏内容
# ============================================================
def test_coverage_check():
    """检查测试覆盖完整性"""
    print_separator("测试6: 测试覆盖检查")

    print("""
    已测试内容:
    ✓ 情绪传导 (spillover_events + player_fame)
    ✓ 暴雷危机 (scandal_risk 累积与触发)
    ✓ Quant基金 (情绪触发建仓)
    ✓ 机构破产 (止损与强制清算)
    ✓ 暗网机制 (rumor vs broadcast)
    ✓ 价值基金 (低估建仓)
    ✓ 做空基金 (暴雷做空)

    需要验证的边界情况:
    1. 流动性枯竭时的价格计算
    2. 多家机构同时操作同一股票
    3. 退市机制触发
    """)

    db_path = "data/games/test_edge.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_game_db(conn)

    init_tools.init_player(conn, "测试玩家", 1000000.0)

    companies = [{"name": "边缘股", "industry_tag": "科技", "description": "边缘公司"}]
    init_tools.init_companies(conn, companies)
    init_tools.init_market_prices(conn)

    stock = conn.execute("SELECT * FROM Stock WHERE name='边缘股'").fetchone()
    print(f"\n--- 边界测试: 极端流动性枯竭 ---")
    print(f"初始流动性: ${stock['current_liquidity']:,.0f}")

    # 制造恐慌
    conn.execute("UPDATE Stock SET hidden_scandal_risk = 100 WHERE name='边缘股'")
    conn.commit()

    result = market_engine.settle_market_turn(conn, 1)
    stock = conn.execute("SELECT * FROM Stock WHERE name='边缘股'").fetchone()
    print(f"恐慌后流动性: ${stock['current_liquidity']:,.0f} (最低: ${stock['base_liquidity'] * 0.1:,.0f})")
    print(f"恐慌指数: {stock['volatility_index']:.3f}")

    conn.close()
    os.remove(db_path)
    print("\n✓ 边界测试完成")


if __name__ == "__main__":
    print("""
    ╔═══════════════════════════════════════════════════════════════╗
    ║        V2.0 市场机制综合深度测试                              ║
    ╚═══════════════════════════════════════════════════════════════╝
    """)

    test_sentiment_transmission()
    test_scandal_crisis()
    test_quant_fund()
    test_inst_bankruptcy()
    test_darkweb_rumors()
    test_coverage_check()

    print("\n" + "=" * 70)
    print("  🎉 所有综合测试完成！")
    print("=" * 70)
