"""
打工系统工具
包含 apply_job, quit_job
"""
from __future__ import annotations

import json
import random
import sqlite3
from typing import Any

from constants import SALARY_BY_LEVEL


def _json_response(data: dict) -> str:
    """将字典转换为 JSON 字符串"""
    return json.dumps(data, ensure_ascii=False, indent=2)


def _error_response(error_code: str, message: str = "") -> str:
    """生成错误响应"""
    return _json_response({"error": error_code, "message": message})


# ── 打工系统工具 ──────────────────────────────────────

def apply_job(conn: sqlite3.Connection, company_id: int, position_level: str = "entry") -> str:
    """
    申请入职
    
    Args:
        conn: 游戏数据库连接
        company_id: 公司ID
        position_level: 申请的职位级别 ("entry"=基层, "middle"=中层, "high"=高管)
    
    Returns:
        str: JSON 格式的响应
    """
    try:
        player = conn.execute("SELECT * FROM Player WHERE id=1").fetchone()
        if not player:
            return _error_response("PLAYER_NOT_FOUND", "玩家不存在")
        
        if player["current_job_company_id"]:
            company = conn.execute(
                "SELECT name FROM Stock WHERE id=?", 
                (player["current_job_company_id"],)
            ).fetchone()
            current_company = company["name"] if company else "某公司"
            return _error_response(
                "ALREADY_EMPLOYED", 
                f"你已经在 {current_company} 工作了，先辞职再申请新工作"
            )
        
        target_company = conn.execute(
            "SELECT * FROM Stock WHERE id=?", (company_id,)
        ).fetchone()
        if not target_company:
            return _error_response("COMPANY_NOT_FOUND", f"公司ID {company_id} 不存在")
        
        fame = player["fame"] if player["fame"] else 0
        cash = player["cash"] if player["cash"] else 0
        
        company_size = target_company["current_liquidity"] if target_company["current_liquidity"] else 1000000
        company_scale = "small"
        if company_size > 5000000:
            company_scale = "large"
        elif company_size > 2000000:
            company_scale = "medium"
        
        company_scale_text = {"small": "小公司", "medium": "中型公司", "large": "巨头公司"}
        
        scale_difficulty = {
            "small": {"entry": 0.9, "middle": 0.7, "high": 0.5},
            "medium": {"entry": 0.7, "middle": 0.5, "high": 0.3},
            "large": {"entry": 0.5, "middle": 0.3, "high": 0.1},
        }
        
        base_success = scale_difficulty.get(company_scale, {}).get(position_level, 0.5)
        
        fame_bonus = min(0.3, fame / 100)
        
        if position_level == "entry":
            min_fame = 0
            if company_scale == "large" and fame < 10:
                base_success = base_success * 0.5
        elif position_level == "middle":
            min_fame = 20
            if company_scale == "large":
                base_success = base_success * 0.7
        else:
            min_fame = 50
            if company_scale == "large":
                base_success = base_success * 0.5
        
        if fame < min_fame:
            return _error_response(
                "FAME_TOO_LOW",
                f"你的名声值只有 {fame}，{target_company['name']} 是{company_scale_text.get(company_scale, '公司')}，"
                f"无法申请 {position_level} 职位。申请该级别职位需要至少 {min_fame} 点名声。"
            )
        
        success_rate = min(0.95, base_success + fame_bonus)
        
        roll = random.random()
        success = roll < success_rate
        
        if success:
            conn.execute(
                """UPDATE Player SET 
                    current_job_company_id = ?,
                    job_level = 1,
                    job_performance = 0
                WHERE id=1""",
                (company_id,)
            )
            
            positions = {
                "entry": "基层员工",
                "middle": "中层管理",
                "high": "高管"
            }
            position_name = positions.get(position_level, "基层员工")
            
            for level_range, amount in SALARY_BY_LEVEL.items():
                if 1 in level_range:
                    salary = amount
                    break
            
            conn.commit()
            
            return _json_response({
                "success": True,
                "outcome": "hired",
                "company_id": company_id,
                "company_name": target_company["name"],
                "company_scale": company_scale,
                "position": position_name,
                "job_level": 1,
                "monthly_salary": salary,
                "narrative": f"恭喜！你成功通过了 {target_company['name']}（{company_scale_text.get(company_scale, '')}）的面试，入职成为 {position_name}。月薪 ${salary:,}。好好干！"
            })
        else:
            reasons = [
                "面试官觉得你经验不足",
                "岗位竞争激烈，你未能脱颖而出",
                "你的简历不够出色",
                "他们选择了其他候选人"
            ]
            reason = random.choice(reasons)
            return _json_response({
                "success": False,
                "outcome": "rejected",
                "company_id": company_id,
                "company_name": target_company["name"],
                "success_rate": success_rate,
                "narrative": f"很遗憾，{target_company['name']} 的面试官觉得你不太合适：{reason}。你的申请被拒绝了。再接再厉！"
            })
    
    except Exception as e:
        return _error_response("APPLY_JOB_FAILED", str(e))


def quit_job(conn: sqlite3.Connection) -> str:
    """
    离职
    
    Args:
        conn: 游戏数据库连接
    
    Returns:
        str: JSON 格式的响应
    """
    try:
        player = conn.execute("SELECT * FROM Player WHERE id=1").fetchone()
        if not player:
            return _error_response("PLAYER_NOT_FOUND", "玩家不存在")
        
        if not player["current_job_company_id"]:
            return _error_response("NOT_EMPLOYED", "你没有工作，不需要离职")
        
        company = conn.execute(
            "SELECT name FROM Stock WHERE id=?", 
            (player["current_job_company_id"],)
        ).fetchone()
        
        company_name = company["name"] if company else "某公司"
        
        conn.execute(
            """UPDATE Player SET 
                current_job_company_id = NULL,
                job_level = 0,
                job_performance = 0
            WHERE id=1"""
        )
        conn.commit()
        
        return _json_response({
            "success": True,
            "outcome": "quit",
            "previous_company": company_name,
            "narrative": f"你向 {company_name} 提交了辞职信，办理完离职手续后，你恢复了自由身。现在你可以重新找工作了。"
        })
    
    except Exception as e:
        return _error_response("QUIT_JOB_FAILED", str(e))


def get_job_info(conn: sqlite3.Connection) -> str:
    """
    查询当前工作状态
    
    Args:
        conn: 游戏数据库连接
    
    Returns:
        str: JSON 格式的响应
    """
    try:
        player = conn.execute("SELECT * FROM Player WHERE id=1").fetchone()
        if not player:
            return _error_response("PLAYER_NOT_FOUND", "玩家不存在")
        
        if not player["current_job_company_id"]:
            return _json_response({
                "employed": False,
                "message": "你目前没有工作"
            })
        
        company = conn.execute(
            "SELECT name, industry_tag FROM Stock WHERE id=?", 
            (player["current_job_company_id"],)
        ).fetchone()
        
        positions = {1: "基层员工", 2: "基层员工", 3: "中层管理", 4: "中层管理", 5: "高管"}
        position = positions.get(player["job_level"], "基层员工")
        
        return _json_response({
            "employed": True,
            "company_id": player["current_job_company_id"],
            "company_name": company["name"] if company else "未知",
            "industry_tag": company["industry_tag"] if company else "未知",
            "job_level": player["job_level"],
            "position": position,
            "job_performance": player["job_performance"] if player["job_performance"] else 0,
            "narrative": f"你在 {company['name']} 担任 {position}，绩效积分: {player['job_performance'] if player['job_performance'] else 0}"
        })
    
    except Exception as e:
        return _error_response("GET_JOB_INFO_FAILED", str(e))


# ── MCP 工具封装 ──────────────────────────────────────

def tool_apply_job(conn: sqlite3.Connection, company_id: int, position_level: str = "entry") -> str:
    """MCP 工具：申请入职"""
    if conn is None:
        return _error_response("NO_ACTIVE_GAME", "没有激活的游戏")
    return apply_job(conn, company_id, position_level)


def tool_quit_job(conn: sqlite3.Connection) -> str:
    """MCP 工具：离职"""
    if conn is None:
        return _error_response("NO_ACTIVE_GAME", "没有激活的游戏")
    return quit_job(conn)


def tool_get_job_info(conn: sqlite3.Connection) -> str:
    """MCP 工具：查询工作状态"""
    if conn is None:
        return _error_response("NO_ACTIVE_GAME", "没有激活的游戏")
    return get_job_info(conn)
