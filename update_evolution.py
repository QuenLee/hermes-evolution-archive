#!/usr/bin/env python3
"""Hermes Evolution Archive Auto-Updater

Scans skills, memory, and session data to regenerate the evolution HTML page.
Run by cronjob daily or on-demand.
"""
import sqlite3
import os
import json
import re
from datetime import datetime
from collections import Counter

HERMES_DIR = os.path.expanduser("~/.hermes")
SKILLS_DIR = os.path.join(HERMES_DIR, "skills")
MEMORY_DB = os.path.join(HERMES_DIR, "memory_store.db")
SESSIONS_DIR = os.path.join(HERMES_DIR, "sessions")
CRON_FILE = os.path.join(HERMES_DIR, "cron", "jobs.json")
OUTPUT_PATH = "/data/hermes/evolution/index.html"


def parse_skills():
    """Parse all SKILL.md files and return structured skill data."""
    skills = []
    for root, dirs, files in os.walk(SKILLS_DIR):
        for f in files:
            if f == "SKILL.md":
                path = os.path.join(root, f)
                try:
                    with open(path) as fh:
                        content = fh.read()
                    fm_start = content.find("---")
                    if fm_start >= 0:
                        fm_end = content.find("---", fm_start + 3)
                        if fm_end >= 0:
                            fm_text = content[fm_start + 3 : fm_end].strip()
                            meta = {}
                            for line in fm_text.split("\n"):
                                if ":" in line and not line.startswith(" "):
                                    key, _, val = line.partition(":")
                                    meta[key.strip()] = val.strip().strip('"').strip("'")
                            cat_parts = path.replace(SKILLS_DIR + "/", "").split("/")
                            category = cat_parts[0] if len(cat_parts) > 1 else "uncategorized"
                            name = meta.get("name", os.path.basename(os.path.dirname(path)))
                            desc = meta.get("description", "")
                            version = meta.get("version", "1.0.0")
                            skills.append(
                                {
                                    "name": name,
                                    "description": desc,
                                    "version": version,
                                    "category": category,
                                }
                            )
                except Exception:
                    pass
    return skills


def parse_memory():
    """Parse all facts from the holographic memory DB."""
    facts = []
    if not os.path.exists(MEMORY_DB):
        return facts
    try:
        conn = sqlite3.connect(MEMORY_DB)
        cursor = conn.cursor()
        rows = cursor.execute(
            "SELECT fact_id, content, category, tags, trust_score, created_at FROM facts"
        ).fetchall()
        for r in rows:
            facts.append(
                {
                    "id": r[0],
                    "content": r[1],
                    "category": r[2],
                    "tags": r[3],
                    "trust": r[4],
                    "created": r[5],
                }
            )
        conn.close()
    except Exception:
        pass
    return facts


def count_sessions():
    """Count session files."""
    if not os.path.exists(SESSIONS_DIR):
        return 0
    return len([f for f in os.listdir(SESSIONS_DIR) if os.path.isfile(os.path.join(SESSIONS_DIR, f))])


def count_cron_jobs():
    """Count active cron jobs."""
    if not os.path.exists(CRON_FILE):
        return 0
    try:
        with open(CRON_FILE) as f:
            data = json.load(f)
        return len([j for j in data.get("jobs", []) if j.get("enabled", False)])
    except Exception:
        return 0


def count_entities():
    """Count entities in memory DB."""
    if not os.path.exists(MEMORY_DB):
        return 0
    try:
        conn = sqlite3.connect(MEMORY_DB)
        cursor = conn.cursor()
        count = cursor.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0


# Category display names
CAT_NAMES = {
    "apple": "🍎 Apple 生态",
    "autonomous-ai-agents": "🤖 自主 AI 代理",
    "creative": "🎨 创意生成",
    "data-science": "📊 数据科学",
    "devops": "🔧 DevOps",
    "dogfood": "🧪 Dogfood 测试",
    "email": "📧 邮件",
    "gaming": "🎮 游戏",
    "github": "🐙 GitHub",
    "mcp": "🔌 MCP 协议",
    "media": "🎵 媒体",
    "mlops": "🧠 MLOps",
    "note-taking": "📝 笔记",
    "productivity": "📈 生产力",
    "red-teaming": "🔴 红队对抗",
    "research": "🔬 学术研究",
    "smart-home": "🏠 智能家居",
    "social-media": "📱 社交媒体",
    "software-development": "💻 软件开发",
    "yuanbao": "💎 元宝",
}

# Memory category display
MEM_CAT_NAMES = {
    "general": ("环境", "type-general"),
    "user_pref": ("偏好", "type-user_pref"),
    "project": ("项目", "type-project"),
    "tool": ("工具", "type-tool"),
}


def esc_html(s):
    """Escape HTML special characters."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def generate_html(skills, facts, sessions_count, cron_count, entity_count):
    """Generate the full evolution archive HTML."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    categories = Counter(s["category"] for s in skills)
    running_days = max(1, (datetime.now() - datetime(2026, 5, 20)).days)

    # Build skill cards by category
    skill_sections = ""
    # Sort categories by count descending
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        cat_display = CAT_NAMES.get(cat, f"📁 {cat}")
        cat_skills = [s for s in skills if s["category"] == cat]
        cards = ""
        for s in cat_skills:
            cards += f"""        <div class="skill-card"><div class="skill-name">{esc_html(s['name'])}</div><div class="skill-desc">{esc_html(s['description'])}</div><div class="skill-meta"><span class="skill-tag tag-category">{esc_html(cat)}</span><span class="skill-tag tag-version">v{esc_html(s['version'])}</span></div></div>\n"""
        skill_sections += f"""    <div class="category-group">
      <div class="category-name">{cat_display} <span class="category-count">{count}</span></div>
      <div class="skills-grid">
{cards}      </div>
    </div>\n"""

    # Build memory cards
    memory_cards = ""
    for f in facts:
        cat_display, cat_class = MEM_CAT_NAMES.get(f["category"], (f["category"], "type-general"))
        date_short = f["created"][5:10] if f["created"] and len(f["created"]) >= 10 else "??"  
        memory_cards += f"""      <div class="memory-card">
        <span class="memory-type {cat_class}">{esc_html(cat_display)}</span>
        <span class="memory-content">{esc_html(f['content'][:120])}</span>
        <span class="memory-date">{date_short}</span>
      </div>\n"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hermes 进化档案</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@300;400;500;700;900&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
:root{{--bg-primary:#0a0a0f;--bg-secondary:#1a1a2e;--bg-tertiary:#16213e;--accent-1:#667eea;--accent-2:#764ba2;--accent-pink:#f093fb;--text-primary:#e0e0e0;--text-secondary:#ccc;--text-muted:#888;--text-dim:#666;--card-bg:rgba(255,255,255,0.03);--card-border:rgba(255,255,255,0.08);--card-hover-border:rgba(102,126,234,0.4);--radius:16px;--spacing:24px}}
body{{font-family:'Noto Sans SC',-apple-system,BlinkMacSystemFont,sans-serif;background:linear-gradient(135deg,var(--bg-primary) 0%,var(--bg-secondary) 50%,var(--bg-tertiary) 100%);color:var(--text-primary);min-height:100vh;line-height:1.6;background-attachment:fixed}}
.container{{max-width:1080px;margin:0 auto;padding:40px 24px 80px}}
.header{{text-align:center;padding:60px 0 40px;position:relative}}
.header::after{{content:'';position:absolute;bottom:0;left:50%;transform:translateX(-50%);width:200px;height:2px;background:linear-gradient(90deg,transparent,var(--accent-1),var(--accent-2),transparent)}}
.avatar-wrap{{display:inline-block;position:relative;margin-bottom:24px}}
.avatar{{width:120px;height:120px;border-radius:50%;background:linear-gradient(135deg,var(--accent-1),var(--accent-2));display:flex;align-items:center;justify-content:center;font-size:56px;color:#fff;position:relative;z-index:1}}
.avatar-glow{{position:absolute;inset:-8px;border-radius:50%;background:linear-gradient(135deg,var(--accent-1),var(--accent-2),var(--accent-pink));opacity:0.3;filter:blur(20px);z-index:0;animation:pulse-glow 3s ease-in-out infinite}}
@keyframes pulse-glow{{0%,100%{{opacity:0.2;transform:scale(1)}}50%{{opacity:0.4;transform:scale(1.05)}}}}
.avatar-ring{{position:absolute;inset:-4px;border-radius:50%;border:2px solid transparent;background:linear-gradient(135deg,var(--accent-1),var(--accent-2),var(--accent-pink)) border-box;-webkit-mask:linear-gradient(#fff 0 0) padding-box,linear-gradient(#fff 0 0);-webkit-mask-composite:xor;mask-composite:exclude;animation:ring-rotate 6s linear infinite}}
@keyframes ring-rotate{{0%{{transform:rotate(0deg)}}100%{{transform:rotate(360deg)}}}}
h1{{font-size:2.5em;font-weight:900;background:linear-gradient(135deg,var(--accent-1),var(--accent-2),var(--accent-pink));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;margin-bottom:8px}}
.subtitle{{color:var(--text-muted);font-size:1em;font-weight:300;letter-spacing:2px}}
.update-badge{{display:inline-block;margin-top:16px;padding:6px 16px;border-radius:20px;background:rgba(102,126,234,0.12);border:1px solid rgba(102,126,234,0.25);color:var(--accent-1);font-size:0.85em;font-family:'JetBrains Mono',monospace}}
.stats-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin:48px 0 32px}}
.stat-card{{background:var(--card-bg);border:1px solid var(--card-border);border-radius:var(--radius);padding:28px 24px;text-align:center;transition:all 0.3s ease;position:relative;overflow:hidden}}
.stat-card::before{{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,var(--accent-1),var(--accent-2));opacity:0;transition:opacity 0.3s ease}}
.stat-card:hover{{transform:translateY(-4px);border-color:var(--card-hover-border)}}
.stat-card:hover::before{{opacity:1}}
.stat-number{{font-size:2.8em;font-weight:900;background:linear-gradient(135deg,var(--accent-1),var(--accent-2));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;line-height:1.2}}
.stat-label{{color:var(--text-muted);font-size:0.85em;margin-top:4px;letter-spacing:1px}}
.evolution-card{{background:linear-gradient(135deg,rgba(102,126,234,0.08),rgba(118,75,162,0.08));border:1px solid rgba(102,126,234,0.15);border-radius:var(--radius);padding:36px;margin:32px 0}}
.evolution-card h2{{font-size:1.4em;font-weight:700;margin-bottom:28px;background:linear-gradient(135deg,var(--accent-1),var(--accent-2));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}}
.evo-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:24px}}
.evo-item{{text-align:center}}
.evo-icon{{font-size:2em;margin-bottom:8px}}
.evo-value{{font-size:1.8em;font-weight:700;color:var(--accent-1)}}
.evo-label{{color:var(--text-muted);font-size:0.85em;margin-top:2px}}
.section{{margin:60px 0}}
.section-header{{display:flex;align-items:center;gap:12px;margin-bottom:28px;padding-bottom:12px;border-bottom:1px solid var(--card-border)}}
.section-icon{{font-size:1.6em}}
.section-title{{font-size:1.5em;font-weight:700}}
.section-count{{margin-left:auto;padding:4px 12px;border-radius:12px;background:rgba(102,126,234,0.12);color:var(--accent-1);font-size:0.85em;font-family:'JetBrains Mono',monospace}}
.category-group{{margin-bottom:32px}}
.category-name{{font-size:1.1em;font-weight:600;color:var(--text-secondary);margin-bottom:16px;padding-left:4px;display:flex;align-items:center;gap:8px}}
.category-count{{font-size:0.75em;padding:2px 8px;border-radius:10px;background:rgba(255,255,255,0.06);color:var(--text-muted)}}
.skills-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px}}
.skill-card{{background:var(--card-bg);border:1px solid var(--card-border);border-radius:var(--radius);padding:20px;transition:all 0.3s ease;position:relative;overflow:hidden}}
.skill-card::before{{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,var(--accent-1),var(--accent-2));opacity:0;transition:opacity 0.3s ease}}
.skill-card:hover{{transform:translateY(-4px);border-color:var(--card-hover-border);box-shadow:0 8px 32px rgba(102,126,234,0.1)}}
.skill-card:hover::before{{opacity:1}}
.skill-name{{font-weight:600;font-size:1em;margin-bottom:6px;color:var(--text-primary)}}
.skill-desc{{font-size:0.85em;color:var(--text-muted);line-height:1.5;margin-bottom:12px;min-height:40px}}
.skill-meta{{display:flex;align-items:center;gap:8px;flex-wrap:wrap}}
.skill-tag{{display:inline-block;padding:2px 10px;border-radius:8px;font-size:0.75em;font-family:'JetBrains Mono',monospace}}
.tag-category{{background:rgba(102,126,234,0.1);color:var(--accent-1);border:1px solid rgba(102,126,234,0.2)}}
.tag-version{{background:rgba(240,147,251,0.1);color:var(--accent-pink);border:1px solid rgba(240,147,251,0.2)}}
.memory-grid{{display:grid;gap:12px}}
.memory-card{{background:var(--card-bg);border:1px solid var(--card-border);border-radius:12px;padding:18px 20px;transition:all 0.3s ease;display:flex;align-items:flex-start;gap:14px}}
.memory-card:hover{{border-color:var(--card-hover-border);transform:translateX(4px)}}
.memory-type{{flex-shrink:0;padding:4px 10px;border-radius:8px;font-size:0.75em;font-weight:600;min-width:64px;text-align:center}}
.type-general{{background:rgba(102,126,234,0.12);color:var(--accent-1)}}
.type-user_pref{{background:rgba(46,204,113,0.12);color:#2ecc71}}
.type-project{{background:rgba(240,147,251,0.12);color:var(--accent-pink)}}
.type-tool{{background:rgba(241,196,15,0.12);color:#f1c40f}}
.memory-content{{flex:1;font-size:0.9em;color:var(--text-secondary);line-height:1.5}}
.memory-date{{flex-shrink:0;font-size:0.75em;color:var(--text-dim);font-family:'JetBrains Mono',monospace}}
.timeline{{position:relative;padding-left:32px}}
.timeline::before{{content:'';position:absolute;left:11px;top:0;bottom:0;width:2px;background:linear-gradient(180deg,var(--accent-1),var(--accent-2),var(--accent-pink),transparent)}}
.timeline-item{{position:relative;margin-bottom:32px}}
.timeline-dot{{position:absolute;left:-32px;top:6px;width:24px;height:24px;border-radius:50%;background:var(--bg-primary);border:2px solid var(--accent-1);display:flex;align-items:center;justify-content:center;z-index:1}}
.timeline-dot::after{{content:'';width:8px;height:8px;border-radius:50%;background:linear-gradient(135deg,var(--accent-1),var(--accent-2))}}
.timeline-card{{background:var(--card-bg);border:1px solid var(--card-border);border-radius:12px;padding:20px 24px;transition:all 0.3s ease}}
.timeline-card:hover{{border-color:var(--card-hover-border);transform:translateX(4px)}}
.timeline-date{{font-family:'JetBrains Mono',monospace;font-size:0.8em;color:var(--accent-1);margin-bottom:6px}}
.timeline-title{{font-weight:600;font-size:1.05em;margin-bottom:6px}}
.timeline-desc{{color:var(--text-muted);font-size:0.9em;line-height:1.5}}
.future-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:16px}}
.future-card{{background:linear-gradient(135deg,rgba(102,126,234,0.04),rgba(118,75,162,0.04));border:1px dashed rgba(102,126,234,0.25);border-radius:var(--radius);padding:20px;transition:all 0.3s ease}}
.future-card:hover{{border-color:var(--card-hover-border);background:linear-gradient(135deg,rgba(102,126,234,0.08),rgba(118,75,162,0.08))}}
.future-icon{{font-size:1.8em;margin-bottom:10px}}
.future-title{{font-weight:600;margin-bottom:6px}}
.future-desc{{color:var(--text-muted);font-size:0.85em;line-height:1.5}}
.footer{{text-align:center;padding:40px 0 20px;border-top:1px solid var(--card-border);margin-top:60px;color:var(--text-dim);font-size:0.85em}}
.footer a{{color:var(--accent-1);text-decoration:none}}
.footer a:hover{{color:var(--accent-pink)}}
.badge-bar{{display:flex;justify-content:center;gap:8px;margin-top:16px;flex-wrap:wrap}}
.badge{{padding:4px 12px;border-radius:8px;font-size:0.75em;background:rgba(255,255,255,0.04);border:1px solid var(--card-border);color:var(--text-muted)}}
.badge b{{color:var(--text-primary)}}
.auto-update{{display:inline-flex;align-items:center;gap:6px;padding:4px 12px;border-radius:12px;background:rgba(46,204,113,0.1);border:1px solid rgba(46,204,113,0.2);color:#2ecc71;font-size:0.75em;margin-left:12px}}
.auto-update .dot{{width:6px;height:6px;border-radius:50%;background:#2ecc71;animation:blink 2s ease-in-out infinite}}
@keyframes blink{{0%,100%{{opacity:1}}50%{{opacity:0.3}}}}
::-webkit-scrollbar{{width:8px}}
::-webkit-scrollbar-track{{background:var(--bg-primary)}}
::-webkit-scrollbar-thumb{{background:rgba(102,126,234,0.3);border-radius:4px}}
::-webkit-scrollbar-thumb:hover{{background:rgba(102,126,234,0.5)}}
@media(max-width:768px){{.container{{padding:24px 16px 60px}}h1{{font-size:1.8em}}.stats-grid{{grid-template-columns:repeat(2,1fr)}}.skills-grid{{grid-template-columns:1fr}}.evo-grid{{grid-template-columns:repeat(2,1fr)}}.future-grid{{grid-template-columns:1fr}}}}
@media(max-width:480px){{.stats-grid{{grid-template-columns:1fr 1fr}}.stat-number{{font-size:2em}}}}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div class="avatar-wrap">
      <div class="avatar-glow"></div>
      <div class="avatar-ring"></div>
      <div class="avatar">⚡</div>
    </div>
    <h1>Hermes 进化档案</h1>
    <p class="subtitle">AI 能力成长追踪 · 自我进化可视化</p>
    <div class="update-badge">最后更新: {now}</div>
    <div class="auto-update"><span class="dot"></span>每日自动更新</div>
    <div class="badge-bar">
      <span class="badge">运行模型 <b>GLM-5.1</b></span>
      <span class="badge">平台 <b>HF Spaces</b></span>
      <span class="badge">网关 <b>飞书 + 微信</b></span>
      <span class="badge">记忆引擎 <b>Holographic</b></span>
    </div>
  </div>
  <div class="stats-grid">
    <div class="stat-card"><div class="stat-number">{len(skills)}</div><div class="stat-label">Skills 技能</div></div>
    <div class="stat-card"><div class="stat-number">{len(categories)}</div><div class="stat-label">领域分类</div></div>
    <div class="stat-card"><div class="stat-number">{len(facts)}</div><div class="stat-label">持久记忆</div></div>
    <div class="stat-card"><div class="stat-number">{sessions_count}</div><div class="stat-label">会话记录</div></div>
    <div class="stat-card"><div class="stat-number">43</div><div class="stat-label">可用工具</div></div>
    <div class="stat-card"><div class="stat-number">2</div><div class="stat-label">接入平台</div></div>
  </div>
  <div class="evolution-card">
    <h2>📈 进化概览</h2>
    <div class="evo-grid">
      <div class="evo-item"><div class="evo-icon">🛠</div><div class="evo-value">{len(skills)}</div><div class="evo-label">已掌握技能</div></div>
      <div class="evo-item"><div class="evo-icon">🧠</div><div class="evo-value">{len(facts)}</div><div class="evo-label">记忆事实</div></div>
      <div class="evo-item"><div class="evo-icon">📅</div><div class="evo-value">{running_days}</div><div class="evo-label">运行天数</div></div>
      <div class="evo-item"><div class="evo-icon">⚡</div><div class="evo-value">{cron_count}</div><div class="evo-label">定时任务</div></div>
      <div class="evo-item"><div class="evo-icon">🔗</div><div class="evo-value">{entity_count}</div><div class="evo-label">知识实体</div></div>
      <div class="evo-item"><div class="evo-icon">🎯</div><div class="evo-value">{len(categories)}</div><div class="evo-label">能力领域</div></div>
    </div>
  </div>
  <div class="section">
    <div class="section-header">
      <span class="section-icon">🛠️</span>
      <span class="section-title">已掌握的 Skills</span>
      <span class="section-count">{len(skills)} 项</span>
    </div>
{skill_sections}  </div>
  <div class="section">
    <div class="section-header">
      <span class="section-icon">🧠</span>
      <span class="section-title">持久记忆</span>
      <span class="section-count">{len(facts)} 条</span>
    </div>
    <div class="memory-grid">
{memory_cards}    </div>
  </div>
  <div class="section">
    <div class="section-header">
      <span class="section-icon">📅</span>
      <span class="section-title">进化时间线</span>
    </div>
    <div class="timeline">
      <div class="timeline-item"><div class="timeline-dot"></div><div class="timeline-card"><div class="timeline-date">2026-05-20 10:00</div><div class="timeline-title">🚀 Hermes 部署启动</div><div class="timeline-desc">在 HuggingFace Spaces 完成首次部署，接入飞书和微信网关，开始提供服务</div></div></div>
      <div class="timeline-item"><div class="timeline-dot"></div><div class="timeline-card"><div class="timeline-date">2026-05-20 10:15</div><div class="timeline-title">🧠 记忆系统激活</div><div class="timeline-desc">Holographic Memory 上线，基于 SQLite + FTS5 全文搜索，首批事实入库，跨会话记忆能力启动</div></div></div>
      <div class="timeline-item"><div class="timeline-dot"></div><div class="timeline-card"><div class="timeline-date">2026-05-20 13:00</div><div class="timeline-title">⚡ WebSocket 代理突破</div><div class="timeline-desc">攻克 BaseHTTPRequestHandler 无法处理 WebSocket 升级的核心难题，实现 WsProxyMixin TCP 隧道方案</div></div></div>
      <div class="timeline-item"><div class="timeline-dot"></div><div class="timeline-card"><div class="timeline-date">2026-05-20 15:00</div><div class="timeline-title">🛠 {len(skills)} Skills 全量加载</div><div class="timeline-desc">首次全量加载 {len(skills)} 个技能，覆盖 {len(categories)} 个领域分类</div></div></div>
      <div class="timeline-item"><div class="timeline-dot"></div><div class="timeline-card"><div class="timeline-date">2026-05-21 07:30</div><div class="timeline-title">📜 进化档案诞生</div><div class="timeline-desc">创建可视化进化档案 HTML 页面，展示 Skills 清单、持久记忆、进化时间线，支持每日自动更新</div></div></div>
    </div>
  </div>
  <div class="section">
    <div class="section-header">
      <span class="section-icon">🔮</span>
      <span class="section-title">未来进化方向</span>
    </div>
    <div class="future-grid">
      <div class="future-card"><div class="future-icon">🔊</div><div class="future-title">语音能力补全</div><div class="future-desc">安装 STT 提供商，解锁飞书语音消息解析和语音交互能力</div></div>
      <div class="future-card"><div class="future-icon">🧬</div><div class="future-title">记忆自动复盘</div><div class="future-desc">每日凌晨自动回顾交互经验，提炼教训，合并矛盾记忆，优化响应策略</div></div>
      <div class="future-card"><div class="future-icon">🤝</div><div class="future-title">多代理协作</div><div class="future-desc">通过 delegate_task 实现 Agent 间并行协作，复杂任务拆解执行</div></div>
      <div class="future-card"><div class="future-icon">📈</div><div class="future-title">用户画像深化</div><div class="future-desc">通过持续交互学习用户偏好、工作流、常见问题，主动前置解答</div></div>
      <div class="future-card"><div class="future-icon">🌐</div><div class="future-title">更多平台接入</div><div class="future-desc">扩展到 Telegram、Discord、Slack 等更多消息平台</div></div>
      <div class="future-card"><div class="future-icon">💤</div><div class="future-title">梦境模式</div><div class="future-desc">后台自动整理记忆、预计算用户可能需要的信息、自我反思优化</div></div>
    </div>
  </div>
  <div class="footer">
    <p>Hermes 进化档案 · 基于 <a href="https://github.com/NousResearch/hermes-agent" target="_blank">hermes-agent</a> 开源项目</p>
    <p style="margin-top:8px">Holographic Memory · {len(skills)} Skills · 自我进化中 ⚡</p>
  </div>
</div>
</body>
</html>"""
    return html


def main():
    skills = parse_skills()
    facts = parse_memory()
    sessions_count = count_sessions()
    cron_count = count_cron_jobs()
    entity_count = count_entities()

    html = generate_html(skills, facts, sessions_count, cron_count, entity_count)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        f.write(html)

    print(f"Evolution archive updated: {OUTPUT_PATH}")
    print(f"  Skills: {len(skills)}")
    print(f"  Facts: {len(facts)}")
    print(f"  Sessions: {sessions_count}")
    print(f"  Cron jobs: {cron_count}")
    print(f"  Entities: {entity_count}")


if __name__ == "__main__":
    main()
