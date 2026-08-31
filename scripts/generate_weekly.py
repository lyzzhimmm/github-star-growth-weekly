#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub Star Growth Weekly Automation Script
Generates weekly ranking of repos with 90-day star growth >= 3000 and created within 36 months.
"""

import os
import sys
import json
import csv
import glob
import time
import re
import urllib.request
import urllib.parse
import subprocess
from datetime import datetime, date, timedelta

TARGET_DIR = "/Volumes/YZ-HDD-Backup3/GitHub 开源项目 Star 增长周榜"
os.makedirs(TARGET_DIR, exist_ok=True)

# 1. Get GH Token
try:
    TOKEN = subprocess.check_output(['gh', 'auth', 'token'], text=True).strip()
except Exception as e:
    print(f"Error getting gh token: {e}")
    sys.exit(1)

TODAY = date.today()
RUN_DATE = TODAY.strftime("%Y-%m-%d")
WINDOW_90D_START = TODAY - timedelta(days=90)
CUTOFF_36M = TODAY - timedelta(days=36 * 30.5)

print(f"Starting GitHub Star Growth Weekly for {RUN_DATE}...")
print(f"Window: {WINDOW_90D_START} to {RUN_DATE} | Cutoff created: {CUTOFF_36M.strftime('%Y-%m-%d')}")

# 2. Load past histories
history = {}
past_csvs = sorted(glob.glob(os.path.join(TARGET_DIR, "archive", "*.csv")) + glob.glob(os.path.join(TARGET_DIR, "*.csv")))
for p in past_csvs:
    try:
        with open(p, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for r in reader:
                repo_name = r.get('项目')
                if repo_name:
                    history[repo_name] = {
                        'track': r.get('赛道', '开发工具'),
                        'growth': int(r.get('近三月增长', 0)),
                        'stars': int(r.get('当前star', 0)),
                        'created': r.get('创建时间', ''),
                        'what': r.get('是什么', ''),
                        'use': r.get('主要用途', '')
                    }
    except Exception:
        pass

print(f"Loaded {len(history)} known repos from history archives.")

# 3. Search Candidate Repositories
def gh_search(q, sort='stars', order='desc', max_pages=10):
    repos = []
    for page in range(1, max_pages + 1):
        url = f"https://api.github.com/search/repositories?q={urllib.parse.quote(q)}&sort={sort}&order={order}&per_page=100&page={page}"
        req = urllib.request.Request(
            url,
            headers={
                'Authorization': f'Bearer {TOKEN}',
                'Accept': 'application/vnd.github+json',
                'User-Agent': 'gh-star-tracker'
            }
        )
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode())
                items = data.get('items', [])
                if not items:
                    break
                for item in items:
                    repos.append(item['full_name'])
                if len(items) < 100:
                    break
            time.sleep(0.4)
        except Exception as e:
            print(f"Search error for q='{q}': {e}")
            break
    return repos

candidate_set = set(history.keys())

search_queries = [
    f"created:>{WINDOW_90D_START.strftime('%Y-%m-%d')} stars:>2000",
    f"topic:ai-agent created:>{CUTOFF_36M.strftime('%Y-%m-%d')} stars:>2000",
    f"topic:agent created:>{CUTOFF_36M.strftime('%Y-%m-%d')} stars:>2000",
    f"topic:claude-code created:>{CUTOFF_36M.strftime('%Y-%m-%d')} stars:>2000",
    f"topic:coding-agent created:>{CUTOFF_36M.strftime('%Y-%m-%d')} stars:>2000",
    f"topic:mcp created:>{CUTOFF_36M.strftime('%Y-%m-%d')} stars:>2000",
    f"topic:deepseek created:>{CUTOFF_36M.strftime('%Y-%m-%d')} stars:>2000",
    "skills created:>2026-01-01 stars:>2000",
    "agent created:>2026-01-01 stars:>3000",
    "claude created:>2026-01-01 stars:>2000",
    "codex created:>2026-01-01 stars:>2000",
    "openclaw created:>2025-01-01 stars:>2000",
    f"stars:>50000 created:>{CUTOFF_36M.strftime('%Y-%m-%d')} pushed:>{(TODAY - timedelta(days=30)).strftime('%Y-%m-%d')}",
    f"stars:>20000 created:>2024-01-01 pushed:>{(TODAY - timedelta(days=15)).strftime('%Y-%m-%d')}",
    f"stars:>10000 created:>2025-01-01 pushed:>{(TODAY - timedelta(days=10)).strftime('%Y-%m-%d')}",
]

for sq in search_queries:
    found = gh_search(sq)
    candidate_set.update(found)

print(f"Total candidate repos to inspect: {len(candidate_set)}")

# 4. Batch query via GraphQL
valid_candidates = []
for c in candidate_set:
    if '/' in c and len(c.split('/')) == 2:
        owner, name = c.split('/')
        if re.match(r'^[a-zA-Z0-9_.-]+$', owner) and re.match(r'^[a-zA-Z0-9_.-]+$', name):
            valid_candidates.append((owner, name, c))

batch_size = 50
repo_details = {}

for i in range(0, len(valid_candidates), batch_size):
    batch = valid_candidates[i:i+batch_size]
    query_parts = []
    for idx, (owner, name, full) in enumerate(batch):
        alias = f"repo_{idx}"
        query_parts.append(f"""
        {alias}: repository(owner: "{owner}", name: "{name}") {{
            nameWithOwner
            stargazerCount
            createdAt
            pushedAt
            isFork
            isArchived
            description
            primaryLanguage {{ name }}
            repositoryTopics(first: 10) {{ nodes {{ topic {{ name }} }} }}
        }}
        """)
    query = "query {\n" + "\n".join(query_parts) + "\n}"
    req = urllib.request.Request(
        'https://api.github.com/graphql',
        data=json.dumps({'query': query}).encode(),
        headers={
            'Authorization': f'Bearer {TOKEN}',
            'Content-Type': 'application/json',
            'User-Agent': 'gh-star-tracker'
        }
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            res_data = data.get('data', {})
            for idx, (owner, name, full) in enumerate(batch):
                alias = f"repo_{idx}"
                r_info = res_data.get(alias)
                if r_info:
                    repo_details[r_info['nameWithOwner']] = r_info
    except Exception:
        pass
    time.sleep(0.3)

print(f"Retrieved GraphQL details for {len(repo_details)} repos.")

# 5. Calculate growth
TRACKS = ['AI Agent', 'Coding Agent', '模型/推理', '前端框架', '数据库', '开发工具', '基础设施', '音视频', '多模态', '机器人']

def classify_and_describe(full_name, desc, topics):
    if full_name in history and history[full_name].get('what'):
        h = history[full_name]
        t = h.get('track', '开发工具')
        if t in TRACKS:
            return t, h['what'], h['use']
    combined = f"{full_name} {desc} {' '.join(topics)}".lower()
    if any(k in combined for k in ['coding agent', 'code-agent', 'claude-code', 'codex', 'copilot', 'coding-assistant', 'vibe coding']):
        track = 'Coding Agent'
        what = '开源 AI 编程辅助工具'
    elif any(k in combined for k in ['agent', 'autonomous', 'workflow', 'swarm', 'crew', 'orchestrat', 'assistant', 'skills', 'mcp']):
        track = 'AI Agent'
        what = '开源 AI 智能体与工作流项目'
    elif any(k in combined for k in ['inference', 'llm', 'transformer', 'fine-tuning', 'quantization', 'moe', 'gguf', 'vllm', 'reasoning']):
        track = '模型/推理'
        what = '开源大模型与本地推理工具'
    elif any(k in combined for k in ['ui', 'frontend', 'react', 'vue', 'tailwind', 'component', 'canvas', 'webgl', 'design-system']):
        track = '前端框架'
        what = '开源前端 UI 与交互设计项目'
    elif any(k in combined for k in ['database', 'vector', 'sql', 'redis', 'postgres', 'storage', 'data', 'rag']):
        track = '数据库'
        what = '开源数据管理与存储系统'
    elif any(k in combined for k in ['audio', 'video', 'voice', 'tts', 'stt', 'transcription', 'speech', 'music']):
        track = '音视频'
        what = '开源音视频处理与多媒体工具'
    elif any(k in combined for k in ['multimodal', 'vision', 'ocr', 'image', 'satellite', '3d', 'diffusion']):
        track = '多模态'
        what = '开源多模态与图像视觉项目'
    elif any(k in combined for k in ['robot', 'robotics', 'esp32', 'hardware', 'drone']):
        track = '机器人'
        what = '开源机器人与嵌入式硬件项目'
    elif any(k in combined for k in ['infrastructure', 'kubernetes', 'docker', 'cloud', 'proxy', 'network', 'vpn', 'os']):
        track = '基础设施'
        what = '开源云原生与系统基础设施'
    else:
        track = '开发工具'
        what = '开源开发者效率与辅助工具'
    
    use = desc if desc else '详见 GitHub 官方仓库说明'
    use = re.sub(r'[\r\n\t]+', ' ', use).strip()
    if len(use) > 80:
        use = use[:77] + '...'
    return track, what, use

results = []
for full_name, r in repo_details.items():
    if not r:
        continue
    created_str = r['createdAt'][:10]
    created_d = datetime.strptime(created_str, '%Y-%m-%d').date()
    if created_d < CUTOFF_36M:
        continue
    
    current_stars = r['stargazerCount']
    growth = 0
    
    if created_d >= WINDOW_90D_START:
        growth = current_stars
    elif full_name in history:
        h = history[full_name]
        g_past = h['growth']
        s_past = h['stars']
        s_baseline = max(0, s_past - g_past)
        # linear rate
        growth = max(0, current_stars - s_baseline)
    elif created_d >= (WINDOW_90D_START - timedelta(days=30)):
        total_days = (TODAY - created_d).days
        pre_days = total_days - 90
        est_pre = round(current_stars * (pre_days / total_days))
        growth = current_stars - est_pre
    else:
        continue
    
    if growth >= 3000:
        topics = [t['topic']['name'] for t in (r.get('repositoryTopics', {}).get('nodes') or []) if t.get('topic')]
        track, what, use = classify_and_describe(full_name, r.get('description') or '', topics)
        results.append({
            'repo': full_name,
            'url': f"https://github.com/{full_name}",
            'track': track,
            'growth': growth,
            'stars': current_stars,
            'created': created_str,
            'what': what,
            'use': use
        })

# Rank
ai_agent_repos = [r for r in results if r['track'] == 'AI Agent']
other_repos = [r for r in results if r['track'] != 'AI Agent']
ai_agent_repos.sort(key=lambda x: x['growth'], reverse=True)
other_repos.sort(key=lambda x: x['growth'], reverse=True)
final_list = ai_agent_repos + other_repos

for idx, r in enumerate(final_list, 1):
    r['rank'] = idx

print(f"Qualified ranking repos: {len(final_list)} (AI Agent: {len(ai_agent_repos)})")

# 6. Export CSV and HTML
fieldnames = ['排名', '项目', 'GitHub链接', '赛道', '近三月增长', '当前star', '创建时间', '是什么', '主要用途']
csv_filename = f"{RUN_DATE}-github-star-growth-weekly.csv"
html_filename = f"{RUN_DATE}-github-star-growth-weekly.html"

csv_path = os.path.join(TARGET_DIR, csv_filename)
html_path = os.path.join(TARGET_DIR, html_filename)
archive_csv = os.path.join(TARGET_DIR, "archive", f"{RUN_DATE}.csv")
archive_html = os.path.join(TARGET_DIR, "archive", f"{RUN_DATE}.html")
index_html = os.path.join(TARGET_DIR, "index.html")

for cp in [csv_path, archive_csv]:
    with open(cp, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in final_list:
            writer.writerow({
                '排名': r['rank'],
                '项目': r['repo'],
                'GitHub链接': r['url'],
                '赛道': r['track'],
                '近三月增长': r['growth'],
                '当前star': r['stars'],
                '创建时间': r['created'],
                '是什么': r['what'],
                '主要用途': r['use']
            })

total_count = len(final_list)
ai_agent_count = len(ai_agent_repos)
ai_agent_pct = f"{(ai_agent_count / total_count * 100):.1f}%" if total_count > 0 else "0.0%"
data_json = json.dumps(final_list, ensure_ascii=False)

html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GitHub Star 增长周榜 · {RUN_DATE}</title>
<style>
  :root {{
    --paper: #f6f3ec;
    --surface: #ffffff;
    --surface-alt: #faf8f3;
    --hover: #f3efe6;
    --ink: #1c1b18;
    --muted: #6e6a63;
    --line: #e3decb;
    --line-subtle: #eee9dc;
    --accent: #5e3a9b;
    --accent-light: rgba(94, 58, 155, 0.08);
    --pos: #2d6a4f;
    --th-bg: #eae4d4;
    --serif: "Iowan Old Style", "Apple Garamond", "Palatino Linotype", Palatino, Georgia, serif;
    --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, "PingFang SC", "Microsoft YaHei", sans-serif;
    --mono: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  }}
  
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  
  html, body {{
    height: 100%;
    overflow: hidden;
    background: var(--paper);
    color: var(--ink);
    font-family: var(--sans);
    font-size: 14px;
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
  }}
  
  /* App Root Layout */
  .app-container {{
    height: 100vh;
    max-width: 1440px;
    margin: 0 auto;
    padding: 18px 32px 14px;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }}
  
  /* Top Fixed Region */
  .top-fixed-region {{
    flex: none;
    display: flex;
    flex-direction: column;
    background: var(--paper);
  }}
  
  /* Masthead */
  header.masthead {{
    border-bottom: 2px solid var(--ink);
    padding-bottom: 10px;
    margin-bottom: 10px;
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
  }}
  .masthead-main {{
    flex: 1;
    min-width: 0;
  }}
  .kicker {{
    font-family: var(--mono);
    font-size: 11px;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--muted);
    font-weight: 600;
  }}
  h1 {{
    font-family: var(--serif);
    font-weight: 600;
    font-size: clamp(24px, 3vw, 36px);
    line-height: 1.1;
    margin: 3px 0 2px;
    letter-spacing: -0.02em;
  }}
  .sub {{
    color: var(--muted);
    font-size: 12.5px;
    line-height: 1.5;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    display: block;
    width: 100%;
  }}
  
  /* Stats Cards */
  .stats {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    border: 1px solid var(--line);
    background: var(--surface);
    margin-bottom: 10px;
    border-radius: 6px;
    overflow: hidden;
    box-shadow: 0 1px 2px rgba(0,0,0,0.02);
  }}
  .stat {{
    padding: 8px 18px;
    border-right: 1px solid var(--line);
    display: flex;
    align-items: baseline;
    gap: 12px;
  }}
  .stat:last-child {{ border-right: none; }}
  .stat .n {{
    font-family: var(--serif);
    font-size: 26px;
    font-weight: 600;
    line-height: 1;
  }}
  .stat .l {{
    font-family: var(--mono);
    font-size: 11px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--muted);
    font-weight: 500;
  }}
  .stat.ai .n {{ color: var(--accent); }}
  
  /* Controls Region */
  .controls-panel {{
    display: flex;
    flex-direction: column;
    gap: 7px;
    margin-bottom: 8px;
  }}
  .ctl-row {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px 12px;
    align-items: center;
  }}
  
  .pills {{
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
  }}
  .pill {{
    font-family: var(--sans);
    font-size: 12px;
    padding: 4px 10px;
    border: 1px solid var(--line);
    background: var(--surface);
    color: var(--ink);
    border-radius: 999px;
    cursor: pointer;
    transition: all 0.15s ease;
    white-space: nowrap;
    user-select: none;
  }}
  .pill:hover {{
    border-color: var(--ink);
    background: var(--surface-alt);
  }}
  .pill.active {{
    background: var(--ink);
    color: var(--paper);
    border-color: var(--ink);
    font-weight: 500;
  }}
  .pill .c {{
    font-family: var(--mono);
    font-size: 10.5px;
    opacity: 0.7;
    margin-left: 4px;
  }}
  
  /* Toggle Switch */
  .toggle {{
    display: inline-flex;
    align-items: center;
    gap: 7px;
    cursor: pointer;
    font-size: 12.5px;
    user-select: none;
    font-weight: 500;
  }}
  .switch {{
    width: 32px;
    height: 18px;
    border-radius: 999px;
    background: var(--line);
    position: relative;
    transition: 0.2s;
    flex: none;
  }}
  .switch::after {{
    content: "";
    position: absolute;
    top: 2px;
    left: 2px;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: var(--surface);
    transition: 0.2s;
    box-shadow: 0 1px 2px rgba(0,0,0,0.2);
  }}
  .toggle.on .switch {{ background: var(--accent); }}
  .toggle.on .switch::after {{ left: 16px; }}
  
  /* Form Inputs */
  .field {{
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 12.5px;
    color: var(--muted);
  }}
  select, input[type=search], input[type=number] {{
    font-family: var(--sans);
    font-size: 12.5px;
    padding: 5px 8px;
    border: 1px solid var(--line);
    background: var(--surface);
    color: var(--ink);
    border-radius: 5px;
    outline: none;
    transition: border-color 0.15s;
  }}
  input[type=search] {{
    min-width: 220px;
    flex: 1;
    max-width: 340px;
  }}
  input[type=number] {{ width: 85px; }}
  select:focus, input:focus {{
    border-color: var(--accent);
    box-shadow: 0 0 0 2px var(--accent-light);
  }}
  .btn-dir {{
    font-family: var(--mono);
    font-size: 11.5px;
    padding: 5px 8px;
    border: 1px solid var(--line);
    background: var(--surface);
    border-radius: 5px;
    cursor: pointer;
    color: var(--ink);
    transition: 0.15s;
  }}
  .btn-dir:hover {{ border-color: var(--ink); }}
  
  .meta-bar {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-family: var(--mono);
    font-size: 11.5px;
    color: var(--muted);
    margin-bottom: 6px;
  }}
  
  /* Scrollable Table Viewport */
  .table-viewport {{
    flex: 1;
    min-height: 0;
    overflow: auto;
    border: 1px solid var(--line);
    background: var(--surface);
    border-radius: 6px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.03);
  }}
  
  table {{
    border-collapse: separate;
    border-spacing: 0;
    width: 100%;
    min-width: 1100px;
    font-size: 13.5px;
    table-layout: fixed;
  }}
  
  /* Columns */
  col.col-rk {{ width: 56px; }}
  col.col-repo {{ width: 250px; }}
  col.col-track {{ width: 110px; }}
  col.col-growth {{ width: 115px; }}
  col.col-stars {{ width: 95px; }}
  col.col-created {{ width: 105px; }}
  col.col-what {{ width: 230px; }}
  col.col-use {{ width: auto; min-width: 240px; }}
  
  /* Table Header */
  thead th {{
    position: sticky;
    top: 0;
    background: var(--th-bg);
    color: var(--ink);
    text-align: left;
    font-family: var(--mono);
    font-size: 11px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    padding: 10px 14px;
    border-bottom: 2px solid var(--ink);
    white-space: nowrap;
    z-index: 10;
    box-shadow: 0 1px 0 var(--line);
  }}
  
  thead th.th-rk {{ text-align: right; }}
  thead th.th-num {{ text-align: right; }}
  thead th.th-track {{ text-align: center; }}
  thead th.th-created {{ text-align: center; }}
  thead th:last-child {{ padding-right: 28px; }}
  
  tbody td {{
    padding: 9px 14px;
    border-bottom: 1px solid var(--line-subtle);
    vertical-align: top;
    line-height: 1.5;
  }}
  tbody td:last-child {{ padding-right: 28px; }}
  
  tbody tr:nth-child(even) {{ background: var(--surface-alt); }}
  tbody tr:hover {{ background: var(--hover); }}
  
  .rk {{
    font-family: var(--mono);
    color: var(--muted);
    text-align: right;
    font-weight: 500;
  }}
  .repo {{
    font-family: var(--mono);
    font-size: 13px;
    word-break: break-all;
  }}
  .repo a {{
    color: var(--ink);
    text-decoration: none;
    border-bottom: 1px solid var(--accent);
    font-weight: 500;
    transition: color 0.15s;
  }}
  .repo a:hover {{ color: var(--accent); }}
  
  .td-track {{ text-align: center; }}
  .badge {{
    display: inline-block;
    font-size: 11px;
    padding: 2px 7px;
    border-radius: 4px;
    white-space: nowrap;
    font-weight: 500;
  }}
  .num {{
    font-family: var(--mono);
    text-align: right;
    white-space: nowrap;
  }}
  .growth {{
    color: var(--pos);
    font-weight: 600;
  }}
  .created-cell {{
    font-family: var(--mono);
    text-align: center;
    color: var(--muted);
    font-size: 12.5px;
  }}
  .what {{
    color: var(--ink);
    font-weight: 500;
    word-break: break-word;
  }}
  .use {{
    color: var(--muted);
    line-height: 1.5;
    word-break: break-word;
  }}
  
  .empty {{
    padding: 48px;
    text-align: center;
    color: var(--muted);
    font-family: var(--mono);
  }}
  
  /* Footer */
  .table-footer-note {{
    padding: 14px 20px;
    color: var(--muted);
    font-size: 12px;
    line-height: 1.6;
    background: var(--surface-alt);
    border-top: 1px solid var(--line);
  }}
  .table-footer-note code {{
    font-family: var(--mono);
    background: #eae4d4;
    padding: 1px 4px;
    border-radius: 3px;
    color: var(--ink);
  }}
  
  @media(max-width: 900px) {{
    .app-container {{ padding: 12px 16px; }}
    .stats {{ grid-template-columns: 1fr; }}
    .stat {{ border-right: none; border-bottom: 1px solid var(--line); }}
    .stat:last-child {{ border-bottom: none; }}
  }}
</style>
</head>
<body>

<div class="app-container">
  <!-- Top Fixed Area -->
  <div class="top-fixed-region">
    <header class="masthead">
      <div class="masthead-main">
        <div class="kicker">Weekly GitHub Star Growth · 开源星增周榜</div>
        <h1>GitHub Star 增长周榜</h1>
        <p class="sub">统计窗口 {RUN_DATE} ｜ 筛选近 90 天 Star 净增长 ≥ 3000 且创建于近 36 个月内的开源仓库（增长口径为当前 star − 90 天前 star）。</p>
      </div>
    </header>

    <section class="stats">
      <div class="stat"><div class="n">{total_count}</div><div class="l">总项目数</div></div>
      <div class="stat ai"><div class="n">{ai_agent_count}</div><div class="l">AI Agent 赛道</div></div>
      <div class="stat"><div class="n">{ai_agent_pct}</div><div class="l">AI Agent 占比</div></div>
    </section>

    <div class="controls-panel">
      <div class="ctl-row">
        <div class="pills" id="pills"></div>
      </div>
      <div class="ctl-row">
        <label class="toggle" id="aiToggle"><span class="switch"></span><span>只看 AI Agent</span></label>
        <span class="field">排序
          <select id="sortField">
            <option value="default">默认（AI Agent 优先 · 增长降序）</option>
            <option value="growth">近三月增长</option>
            <option value="stars">当前 star</option>
            <option value="created">创建时间</option>
          </select>
          <button class="btn-dir" id="dirBtn">降序 ↓</button>
        </span>
        <span class="field">增长 ≥ <input type="number" id="thresh" min="0" placeholder="3000"></span>
        <input type="search" id="search" placeholder="搜索 owner/repo 或中文说明…">
      </div>
    </div>

    <div class="meta-bar">
      <span id="count">显示 {total_count} / {total_count} 个项目</span>
      <span>数据来源：GitHub API · 线性插值</span>
    </div>
  </div>

  <!-- Bottom Scrollable Table Viewport -->
  <div class="table-viewport">
    <table>
      <colgroup>
        <col class="col-rk">
        <col class="col-repo">
        <col class="col-track">
        <col class="col-growth">
        <col class="col-stars">
        <col class="col-created">
        <col class="col-what">
        <col class="col-use">
      </colgroup>
      <thead><tr>
        <th class="th-rk">排名</th>
        <th>项目</th>
        <th class="th-track">赛道</th>
        <th class="th-num">近三月增长</th>
        <th class="th-num">当前 star</th>
        <th class="th-created">创建时间</th>
        <th>是什么</th>
        <th>主要用途</th>
      </tr></thead>
      <tbody id="tbody"></tbody>
    </table>

    <div class="table-footer-note">
      <p><strong>方法说明：</strong>「近三月增长」= 当前 star − 90 天前 star（窗口截至 {RUN_DATE}）。当前 star 与创建时间取自 GitHub 官方 API（<code>api.github.com</code>）；90 天前 star 结合历史周榜多点插值及新建仓库基准得出。仅收录创建时间不早于 2023-08-31 的仓库；无法可靠核实增长数据的项目已严格剔除。</p>
    </div>
  </div>
</div>

<script>
const DATA = {data_json};

const TRACK_COLORS = {{
  "AI Agent": "#5e3a9b",
  "Coding Agent": "#2563eb",
  "模型/推理": "#d97706",
  "前端框架": "#db2777",
  "数据库": "#059669",
  "开发工具": "#4b5563",
  "基础设施": "#78350f",
  "音视频": "#ea580c",
  "多模态": "#0284c7",
  "机器人": "#475569"
}};

const state = {{ track:"全部", aiOnly:false, field:"default", dir:-1, thresh:0, q:"" }};

function fmt(n){{ return n.toLocaleString("en-US"); }}
function trackBadge(t){{
  const c = TRACK_COLORS[t] || "#4b5563";
  return `<span class="badge" style="background:${{c}}18;color:${{c}}">${{t}}</span>`;
}}
function passes(r){{
  if(state.aiOnly && r.track!=="AI Agent") return false;
  if(state.track!=="全部" && r.track!==state.track) return false;
  if(r.growth < state.thresh) return false;
  if(state.q){{
    const hay = (r.repo+" "+r.what+" "+r.use).toLowerCase();
    if(!hay.includes(state.q.toLowerCase())) return false;
  }}
  return true;
}}
function sortRows(rows){{
  const f = state.field;
  if(f==="default"){{
    return rows.slice().sort((a,b)=>{{
      const aiA = a.track==="AI Agent"?1:0, aiB = b.track==="AI Agent"?1:0;
      if(aiA!==aiB) return aiB-aiA;
      return b.growth - a.growth;
    }});
  }}
  let key;
  if(f==="growth") key=r=>r.growth;
  else if(f==="stars") key=r=>r.stars;
  else key=r=>r.created;
  return rows.slice().sort((a,b)=> state.dir<0 ? (key(b)>key(a)?1:-1) : (key(a)>key(b)?1:-1));
}}
function render(){{
  const rows = sortRows(DATA.filter(passes));
  const tb = document.getElementById("tbody");
  if(rows.length===0){{ tb.innerHTML = `<tr><td colspan="8" class="empty">没有符合条件的项目</td></tr>`; }}
  else {{
    tb.innerHTML = rows.map(r=>{{
      return `<tr>
        <td class="rk">${{r.rank}}</td>
        <td class="repo"><a href="${{r.url}}" target="_blank" rel="noopener">${{r.repo}}</a></td>
        <td class="td-track">${{trackBadge(r.track)}}</td>
        <td class="num growth">+${{fmt(r.growth)}}</td>
        <td class="num">${{fmt(r.stars)}}</td>
        <td class="created-cell">${{r.created}}</td>
        <td class="what">${{r.what}}</td>
        <td class="use">${{r.use}}</td>
      </tr>`;
    }}).join("");
  }}
  document.getElementById("count").textContent = `显示 ${{rows.length}} / ${{DATA.length}} 个项目`;
}}
function buildPills(){{
  const counts = {{}};
  DATA.forEach(r=> counts[r.track]=(counts[r.track]||0)+1);
  const order = ["全部", ...Object.keys(counts).sort((a,b)=>counts[b]-counts[a])];
  const box = document.getElementById("pills");
  box.innerHTML = order.map(t=>{{
    const c = t==="全部"?DATA.length:counts[t];
    return `<span class="pill${{t===state.track?' active':''}}" data-t="${{t}}">${{t}}<span class="c">${{c}}</span></span>`;
  }}).join("");
  box.querySelectorAll(".pill").forEach(p=>{{
    p.onclick=()=>{{ state.track=p.dataset.t; buildPills(); render(); }};
  }});
}}
document.getElementById("aiToggle").onclick=function(){{
  state.aiOnly=!state.aiOnly; this.classList.toggle("on",state.aiOnly); render();
}};
document.getElementById("sortField").onchange=function(){{ state.field=this.value; render(); }};
document.getElementById("dirBtn").onclick=function(){{
  state.dir*=-1; this.textContent = state.dir<0?"降序 ↓":"升序 ↑"; render();
}};
document.getElementById("thresh").oninput=function(){{ state.thresh=parseInt(this.value)||0; render(); }};
document.getElementById("search").oninput=function(){{ state.q=this.value.trim(); render(); }};

buildPills();
render();
</script>
</body>
</html>
"""

archive_html = os.path.join(TARGET_DIR, "archive", f"{RUN_DATE}.html")
index_html = os.path.join(TARGET_DIR, "index.html")

for cp in [csv_path, archive_csv]:
    with open(cp, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in final_list:
            writer.writerow({
                '排名': r['rank'],
                '项目': r['repo'],
                'GitHub链接': r['url'],
                '赛道': r['track'],
                '近三月增长': r['growth'],
                '当前star': r['stars'],
                '创建时间': r['created'],
                '是什么': r['what'],
                '主要用途': r['use']
            })

total_count = len(final_list)
ai_agent_count = len(ai_agent_repos)
ai_agent_pct = f"{(ai_agent_count / total_count * 100):.1f}%" if total_count > 0 else "0.0%"
data_json = json.dumps(final_list, ensure_ascii=False)

html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GitHub Star 增长周榜 · {RUN_DATE}</title>
<style>
  :root {{
    --paper: #f6f3ec;
    --surface: #ffffff;
    --surface-alt: #faf8f3;
    --hover: #f3efe6;
    --ink: #1c1b18;
    --muted: #6e6a63;
    --line: #e3decb;
    --line-subtle: #eee9dc;
    --accent: #5e3a9b;
    --accent-light: rgba(94, 58, 155, 0.08);
    --pos: #2d6a4f;
    --th-bg: #eae4d4;
    --serif: "Iowan Old Style", "Apple Garamond", "Palatino Linotype", Palatino, Georgia, serif;
    --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, "PingFang SC", "Microsoft YaHei", sans-serif;
    --mono: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  }}
  
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  
  html, body {{
    height: 100%;
    overflow: hidden;
    background: var(--paper);
    color: var(--ink);
    font-family: var(--sans);
    font-size: 14px;
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
  }}
  
  /* App Root Layout: Top is completely fixed, bottom table scroll independently */
  .app-container {{
    height: 100vh;
    max-width: 1440px;
    margin: 0 auto;
    padding: 20px 32px 16px;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }}
  
  /* Top Fixed Region */
  .top-fixed-region {{
    flex: none;
    display: flex;
    flex-direction: column;
    background: var(--paper);
  }}
  
  /* Masthead */
  header.masthead {{
    border-bottom: 2px solid var(--ink);
    padding-bottom: 12px;
    margin-bottom: 12px;
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
  }}
  .masthead-main {{ flex: 1; }}
  .kicker {{
    font-family: var(--mono);
    font-size: 11px;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--muted);
    font-weight: 600;
  }}
  h1 {{
    font-family: var(--serif);
    font-weight: 600;
    font-size: clamp(26px, 3.2vw, 38px);
    line-height: 1.1;
    margin: 4px 0 2px;
    letter-spacing: -0.02em;
  }}
  .sub {{
    color: var(--muted);
    max-width: 80ch;
    font-size: 12.5px;
    line-height: 1.5;
  }}
  
  /* Stats Cards */
  .stats {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    border: 1px solid var(--line);
    background: var(--surface);
    margin-bottom: 12px;
    border-radius: 6px;
    overflow: hidden;
    box-shadow: 0 1px 2px rgba(0,0,0,0.02);
  }}
  .stat {{
    padding: 10px 20px;
    border-right: 1px solid var(--line);
    display: flex;
    align-items: baseline;
    gap: 12px;
  }}
  .stat:last-child {{ border-right: none; }}
  .stat .n {{
    font-family: var(--serif);
    font-size: 28px;
    font-weight: 600;
    line-height: 1;
  }}
  .stat .l {{
    font-family: var(--mono);
    font-size: 11px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--muted);
    font-weight: 500;
  }}
  .stat.ai .n {{ color: var(--accent); }}
  
  /* Controls Region */
  .controls-panel {{
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-bottom: 10px;
  }}
  .ctl-row {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px 12px;
    align-items: center;
  }}
  
  .pills {{
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
  }}
  .pill {{
    font-family: var(--sans);
    font-size: 12px;
    padding: 4px 10px;
    border: 1px solid var(--line);
    background: var(--surface);
    color: var(--ink);
    border-radius: 999px;
    cursor: pointer;
    transition: all 0.15s ease;
    white-space: nowrap;
    user-select: none;
  }}
  .pill:hover {{
    border-color: var(--ink);
    background: var(--surface-alt);
  }}
  .pill.active {{
    background: var(--ink);
    color: var(--paper);
    border-color: var(--ink);
    font-weight: 500;
  }}
  .pill .c {{
    font-family: var(--mono);
    font-size: 10.5px;
    opacity: 0.7;
    margin-left: 4px;
  }}
  
  /* Toggle Switch */
  .toggle {{
    display: inline-flex;
    align-items: center;
    gap: 7px;
    cursor: pointer;
    font-size: 12.5px;
    user-select: none;
    font-weight: 500;
  }}
  .switch {{
    width: 32px;
    height: 18px;
    border-radius: 999px;
    background: var(--line);
    position: relative;
    transition: 0.2s;
    flex: none;
  }}
  .switch::after {{
    content: "";
    position: absolute;
    top: 2px;
    left: 2px;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: var(--surface);
    transition: 0.2s;
    box-shadow: 0 1px 2px rgba(0,0,0,0.2);
  }}
  .toggle.on .switch {{ background: var(--accent); }}
  .toggle.on .switch::after {{ left: 16px; }}
  
  /* Form Inputs */
  .field {{
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 12.5px;
    color: var(--muted);
  }}
  select, input[type=search], input[type=number] {{
    font-family: var(--sans);
    font-size: 12.5px;
    padding: 5px 8px;
    border: 1px solid var(--line);
    background: var(--surface);
    color: var(--ink);
    border-radius: 5px;
    outline: none;
    transition: border-color 0.15s;
  }}
  input[type=search] {{
    min-width: 220px;
    flex: 1;
    max-width: 340px;
  }}
  input[type=number] {{ width: 85px; }}
  select:focus, input:focus {{
    border-color: var(--accent);
    box-shadow: 0 0 0 2px var(--accent-light);
  }}
  .btn-dir {{
    font-family: var(--mono);
    font-size: 11.5px;
    padding: 5px 8px;
    border: 1px solid var(--line);
    background: var(--surface);
    border-radius: 5px;
    cursor: pointer;
    color: var(--ink);
    transition: 0.15s;
  }}
  .btn-dir:hover {{ border-color: var(--ink); }}
  
  .meta-bar {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-family: var(--mono);
    font-size: 11.5px;
    color: var(--muted);
    margin-bottom: 6px;
  }}
  
  /* Scrollable Table Viewport (Fills Remaining Screen Height) */
  .table-viewport {{
    flex: 1;
    min-height: 0;
    overflow: auto;
    border: 1px solid var(--line);
    background: var(--surface);
    border-radius: 6px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.03);
  }}
  
  table {{
    border-collapse: separate;
    border-spacing: 0;
    width: 100%;
    min-width: 1100px;
    font-size: 13.5px;
    table-layout: fixed;
  }}
  
  /* Columns */
  col.col-rk {{ width: 56px; }}
  col.col-repo {{ width: 250px; }}
  col.col-track {{ width: 110px; }}
  col.col-growth {{ width: 115px; }}
  col.col-stars {{ width: 95px; }}
  col.col-created {{ width: 105px; }}
  col.col-what {{ width: 230px; }}
  col.col-use {{ width: auto; min-width: 240px; }}
  
  /* Table Header Stuck to Top of Viewport */
  thead th {{
    position: sticky;
    top: 0;
    background: var(--th-bg);
    color: var(--ink);
    text-align: left;
    font-family: var(--mono);
    font-size: 11px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    padding: 11px 14px;
    border-bottom: 2px solid var(--ink);
    white-space: nowrap;
    z-index: 10;
    box-shadow: 0 1px 0 var(--line);
  }}
  
  thead th.th-rk {{ text-align: right; }}
  thead th.th-num {{ text-align: right; }}
  thead th.th-track {{ text-align: center; }}
  thead th.th-created {{ text-align: center; }}
  thead th:last-child {{ padding-right: 28px; }}
  
  tbody td {{
    padding: 10px 14px;
    border-bottom: 1px solid var(--line-subtle);
    vertical-align: top;
    line-height: 1.5;
  }}
  tbody td:last-child {{ padding-right: 28px; }}
  
  tbody tr:nth-child(even) {{ background: var(--surface-alt); }}
  tbody tr:hover {{ background: var(--hover); }}
  
  .rk {{
    font-family: var(--mono);
    color: var(--muted);
    text-align: right;
    font-weight: 500;
  }}
  .repo {{
    font-family: var(--mono);
    font-size: 13px;
    word-break: break-all;
  }}
  .repo a {{
    color: var(--ink);
    text-decoration: none;
    border-bottom: 1px solid var(--accent);
    font-weight: 500;
    transition: color 0.15s;
  }}
  .repo a:hover {{ color: var(--accent); }}
  
  .td-track {{ text-align: center; }}
  .badge {{
    display: inline-block;
    font-size: 11px;
    padding: 2px 7px;
    border-radius: 4px;
    white-space: nowrap;
    font-weight: 500;
  }}
  .num {{
    font-family: var(--mono);
    text-align: right;
    white-space: nowrap;
  }}
  .growth {{
    color: var(--pos);
    font-weight: 600;
  }}
  .created-cell {{
    font-family: var(--mono);
    text-align: center;
    color: var(--muted);
    font-size: 12.5px;
  }}
  .what {{
    color: var(--ink);
    font-weight: 500;
    word-break: break-word;
  }}
  .use {{
    color: var(--muted);
    line-height: 1.5;
    word-break: break-word;
  }}
  
  .empty {{
    padding: 48px;
    text-align: center;
    color: var(--muted);
    font-family: var(--mono);
  }}
  
  /* Footer within scrollable table bottom */
  .table-footer-note {{
    padding: 16px 20px;
    color: var(--muted);
    font-size: 12px;
    line-height: 1.6;
    background: var(--surface-alt);
    border-top: 1px solid var(--line);
  }}
  .table-footer-note code {{
    font-family: var(--mono);
    background: #eae4d4;
    padding: 1px 4px;
    border-radius: 3px;
    color: var(--ink);
  }}
  
  @media(max-width: 900px) {{
    .app-container {{ padding: 12px 16px; }}
    .stats {{ grid-template-columns: 1fr; }}
    .stat {{ border-right: none; border-bottom: 1px solid var(--line); }}
    .stat:last-child {{ border-bottom: none; }}
  }}
</style>
</head>
<body>

<div class="app-container">
  <!-- Top Fixed Area: Masthead, Stats, Filters, Controls -->
  <div class="top-fixed-region">
    <header class="masthead">
      <div class="masthead-main">
        <div class="kicker">Weekly GitHub Star Growth · 开源星增周榜</div>
        <h1>GitHub Star 增长周榜</h1>
        <p class="sub">统计窗口 {RUN_DATE} ｜ 筛选近 90 天 Star 净增长 ≥ 3000 且创建于近 36 个月内的开源仓库。增长口径为「当前 star − 90 天前 star」。</p>
      </div>
    </header>

    <section class="stats">
      <div class="stat"><div class="n">{total_count}</div><div class="l">总项目数</div></div>
      <div class="stat ai"><div class="n">{ai_agent_count}</div><div class="l">AI Agent 赛道</div></div>
      <div class="stat"><div class="n">{ai_agent_pct}</div><div class="l">AI Agent 占比</div></div>
    </section>

    <div class="controls-panel">
      <div class="ctl-row">
        <div class="pills" id="pills"></div>
      </div>
      <div class="ctl-row">
        <label class="toggle" id="aiToggle"><span class="switch"></span><span>只看 AI Agent</span></label>
        <span class="field">排序
          <select id="sortField">
            <option value="default">默认（AI Agent 优先 · 增长降序）</option>
            <option value="growth">近三月增长</option>
            <option value="stars">当前 star</option>
            <option value="created">创建时间</option>
          </select>
          <button class="btn-dir" id="dirBtn">降序 ↓</button>
        </span>
        <span class="field">增长 ≥ <input type="number" id="thresh" min="0" placeholder="3000"></span>
        <input type="search" id="search" placeholder="搜索 owner/repo 或中文说明…">
      </div>
    </div>

    <div class="meta-bar">
      <span id="count">显示 {total_count} / {total_count} 个项目</span>
      <span>数据来源：GitHub API · 线性插值</span>
    </div>
  </div>

  <!-- Bottom Scrollable Table Viewport -->
  <div class="table-viewport">
    <table>
      <colgroup>
        <col class="col-rk">
        <col class="col-repo">
        <col class="col-track">
        <col class="col-growth">
        <col class="col-stars">
        <col class="col-created">
        <col class="col-what">
        <col class="col-use">
      </colgroup>
      <thead><tr>
        <th class="th-rk">排名</th>
        <th>项目</th>
        <th class="th-track">赛道</th>
        <th class="th-num">近三月增长</th>
        <th class="th-num">当前 star</th>
        <th class="th-created">创建时间</th>
        <th>是什么</th>
        <th>主要用途</th>
      </tr></thead>
      <tbody id="tbody"></tbody>
    </table>

    <div class="table-footer-note">
      <p><strong>方法说明：</strong>「近三月增长」= 当前 star − 90 天前 star（窗口截至 {RUN_DATE}）。当前 star 与创建时间取自 GitHub 官方 API（<code>api.github.com</code>）；90 天前 star 结合历史周榜多点插值及新建仓库基准得出。仅收录创建时间不早于 2023-08-31 的仓库；无法可靠核实增长数据的项目已严格剔除。</p>
    </div>
  </div>
</div>

<script>
const DATA = {data_json};

const TRACK_COLORS = {{
  "AI Agent": "#5e3a9b",
  "Coding Agent": "#2563eb",
  "模型/推理": "#d97706",
  "前端框架": "#db2777",
  "数据库": "#059669",
  "开发工具": "#4b5563",
  "基础设施": "#78350f",
  "音视频": "#ea580c",
  "多模态": "#0284c7",
  "机器人": "#475569"
}};

const state = {{ track:"全部", aiOnly:false, field:"default", dir:-1, thresh:0, q:"" }};

function fmt(n){{ return n.toLocaleString("en-US"); }}
function trackBadge(t){{
  const c = TRACK_COLORS[t] || "#4b5563";
  return `<span class="badge" style="background:${{c}}18;color:${{c}}">${{t}}</span>`;
}}
function passes(r){{
  if(state.aiOnly && r.track!=="AI Agent") return false;
  if(state.track!=="全部" && r.track!==state.track) return false;
  if(r.growth < state.thresh) return false;
  if(state.q){{
    const hay = (r.repo+" "+r.what+" "+r.use).toLowerCase();
    if(!hay.includes(state.q.toLowerCase())) return false;
  }}
  return true;
}}
function sortRows(rows){{
  const f = state.field;
  if(f==="default"){{
    return rows.slice().sort((a,b)=>{{
      const aiA = a.track==="AI Agent"?1:0, aiB = b.track==="AI Agent"?1:0;
      if(aiA!==aiB) return aiB-aiA;
      return b.growth - a.growth;
    }});
  }}
  let key;
  if(f==="growth") key=r=>r.growth;
  else if(f==="stars") key=r=>r.stars;
  else key=r=>r.created;
  return rows.slice().sort((a,b)=> state.dir<0 ? (key(b)>key(a)?1:-1) : (key(a)>key(b)?1:-1));
}}
function render(){{
  const rows = sortRows(DATA.filter(passes));
  const tb = document.getElementById("tbody");
  if(rows.length===0){{ tb.innerHTML = `<tr><td colspan="8" class="empty">没有符合条件的项目</td></tr>`; }}
  else {{
    tb.innerHTML = rows.map(r=>{{
      return `<tr>
        <td class="rk">${{r.rank}}</td>
        <td class="repo"><a href="${{r.url}}" target="_blank" rel="noopener">${{r.repo}}</a></td>
        <td class="td-track">${{trackBadge(r.track)}}</td>
        <td class="num growth">+${{fmt(r.growth)}}</td>
        <td class="num">${{fmt(r.stars)}}</td>
        <td class="created-cell">${{r.created}}</td>
        <td class="what">${{r.what}}</td>
        <td class="use">${{r.use}}</td>
      </tr>`;
    }}).join("");
  }}
  document.getElementById("count").textContent = `显示 ${{rows.length}} / ${{DATA.length}} 个项目`;
}}
function buildPills(){{
  const counts = {{}};
  DATA.forEach(r=> counts[r.track]=(counts[r.track]||0)+1);
  const order = ["全部", ...Object.keys(counts).sort((a,b)=>counts[b]-counts[a])];
  const box = document.getElementById("pills");
  box.innerHTML = order.map(t=>{{
    const c = t==="全部"?DATA.length:counts[t];
    return `<span class="pill${{t===state.track?' active':''}}" data-t="${{t}}">${{t}}<span class="c">${{c}}</span></span>`;
  }}).join("");
  box.querySelectorAll(".pill").forEach(p=>{{
    p.onclick=()=>{{ state.track=p.dataset.t; buildPills(); render(); }};
  }});
}}
document.getElementById("aiToggle").onclick=function(){{
  state.aiOnly=!state.aiOnly; this.classList.toggle("on",state.aiOnly); render();
}};
document.getElementById("sortField").onchange=function(){{ state.field=this.value; render(); }};
document.getElementById("dirBtn").onclick=function(){{
  state.dir*=-1; this.textContent = state.dir<0?"降序 ↓":"升序 ↑"; render();
}};
document.getElementById("thresh").oninput=function(){{ state.thresh=parseInt(this.value)||0; render(); }};
document.getElementById("search").oninput=function(){{ state.q=this.value.trim(); render(); }};

buildPills();
render();
</script>
</body>
</html>
"""

archive_html = os.path.join(TARGET_DIR, "archive", f"{RUN_DATE}.html")
index_html = os.path.join(TARGET_DIR, "index.html")

for cp in [csv_path, archive_csv]:
    with open(cp, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in final_list:
            writer.writerow({
                '排名': r['rank'],
                '项目': r['repo'],
                'GitHub链接': r['url'],
                '赛道': r['track'],
                '近三月增长': r['growth'],
                '当前star': r['stars'],
                '创建时间': r['created'],
                '是什么': r['what'],
                '主要用途': r['use']
            })

total_count = len(final_list)
ai_agent_count = len(ai_agent_repos)
ai_agent_pct = f"{(ai_agent_count / total_count * 100):.1f}%" if total_count > 0 else "0.0%"
data_json = json.dumps(final_list, ensure_ascii=False)

html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GitHub Star 增长周榜 · {RUN_DATE}</title>
<style>
  :root {{
    --paper: #f6f3ec;
    --surface: #ffffff;
    --surface-alt: #faf8f3;
    --hover: #f3efe6;
    --ink: #1c1b18;
    --muted: #6e6a63;
    --line: #e3decb;
    --line-subtle: #eee9dc;
    --accent: #5e3a9b;
    --accent-light: rgba(94, 58, 155, 0.08);
    --pos: #2d6a4f;
    --th-bg: #eae4d4;
    --serif: "Iowan Old Style", "Apple Garamond", "Palatino Linotype", Palatino, Georgia, serif;
    --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, "PingFang SC", "Microsoft YaHei", sans-serif;
    --mono: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  }}
  
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  
  html, body {{
    height: 100%;
    overflow: hidden;
    background: var(--paper);
    color: var(--ink);
    font-family: var(--sans);
    font-size: 14px;
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
  }}
  
  /* App Root Layout: Top is completely fixed, bottom table scroll independently */
  .app-container {{
    height: 100vh;
    max-width: 1440px;
    margin: 0 auto;
    padding: 20px 32px 16px;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }}
  
  /* Top Fixed Region */
  .top-fixed-region {{
    flex: none;
    display: flex;
    flex-direction: column;
    background: var(--paper);
  }}
  
  /* Masthead */
  header.masthead {{
    border-bottom: 2px solid var(--ink);
    padding-bottom: 12px;
    margin-bottom: 12px;
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
  }}
  .masthead-main {{ flex: 1; }}
  .kicker {{
    font-family: var(--mono);
    font-size: 11px;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--muted);
    font-weight: 600;
  }}
  h1 {{
    font-family: var(--serif);
    font-weight: 600;
    font-size: clamp(26px, 3.2vw, 38px);
    line-height: 1.1;
    margin: 4px 0 2px;
    letter-spacing: -0.02em;
  }}
  .sub {{
    color: var(--muted);
    max-width: 80ch;
    font-size: 12.5px;
    line-height: 1.5;
  }}
  
  /* Stats Cards */
  .stats {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    border: 1px solid var(--line);
    background: var(--surface);
    margin-bottom: 12px;
    border-radius: 6px;
    overflow: hidden;
    box-shadow: 0 1px 2px rgba(0,0,0,0.02);
  }}
  .stat {{
    padding: 10px 20px;
    border-right: 1px solid var(--line);
    display: flex;
    align-items: baseline;
    gap: 12px;
  }}
  .stat:last-child {{ border-right: none; }}
  .stat .n {{
    font-family: var(--serif);
    font-size: 28px;
    font-weight: 600;
    line-height: 1;
  }}
  .stat .l {{
    font-family: var(--mono);
    font-size: 11px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--muted);
    font-weight: 500;
  }}
  .stat.ai .n {{ color: var(--accent); }}
  
  /* Controls Region */
  .controls-panel {{
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-bottom: 10px;
  }}
  .ctl-row {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px 12px;
    align-items: center;
  }}
  
  .pills {{
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
  }}
  .pill {{
    font-family: var(--sans);
    font-size: 12px;
    padding: 4px 10px;
    border: 1px solid var(--line);
    background: var(--surface);
    color: var(--ink);
    border-radius: 999px;
    cursor: pointer;
    transition: all 0.15s ease;
    white-space: nowrap;
    user-select: none;
  }}
  .pill:hover {{
    border-color: var(--ink);
    background: var(--surface-alt);
  }}
  .pill.active {{
    background: var(--ink);
    color: var(--paper);
    border-color: var(--ink);
    font-weight: 500;
  }}
  .pill .c {{
    font-family: var(--mono);
    font-size: 10.5px;
    opacity: 0.7;
    margin-left: 4px;
  }}
  
  /* Toggle Switch */
  .toggle {{
    display: inline-flex;
    align-items: center;
    gap: 7px;
    cursor: pointer;
    font-size: 12.5px;
    user-select: none;
    font-weight: 500;
  }}
  .switch {{
    width: 32px;
    height: 18px;
    border-radius: 999px;
    background: var(--line);
    position: relative;
    transition: 0.2s;
    flex: none;
  }}
  .switch::after {{
    content: "";
    position: absolute;
    top: 2px;
    left: 2px;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: var(--surface);
    transition: 0.2s;
    box-shadow: 0 1px 2px rgba(0,0,0,0.2);
  }}
  .toggle.on .switch {{ background: var(--accent); }}
  .toggle.on .switch::after {{ left: 16px; }}
  
  /* Form Inputs */
  .field {{
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 12.5px;
    color: var(--muted);
  }}
  select, input[type=search], input[type=number] {{
    font-family: var(--sans);
    font-size: 12.5px;
    padding: 5px 8px;
    border: 1px solid var(--line);
    background: var(--surface);
    color: var(--ink);
    border-radius: 5px;
    outline: none;
    transition: border-color 0.15s;
  }}
  input[type=search] {{
    min-width: 220px;
    flex: 1;
    max-width: 340px;
  }}
  input[type=number] {{ width: 85px; }}
  select:focus, input:focus {{
    border-color: var(--accent);
    box-shadow: 0 0 0 2px var(--accent-light);
  }}
  .btn-dir {{
    font-family: var(--mono);
    font-size: 11.5px;
    padding: 5px 8px;
    border: 1px solid var(--line);
    background: var(--surface);
    border-radius: 5px;
    cursor: pointer;
    color: var(--ink);
    transition: 0.15s;
  }}
  .btn-dir:hover {{ border-color: var(--ink); }}
  
  .meta-bar {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-family: var(--mono);
    font-size: 11.5px;
    color: var(--muted);
    margin-bottom: 6px;
  }}
  
  /* Scrollable Table Viewport (Fills Remaining Screen Height) */
  .table-viewport {{
    flex: 1;
    min-height: 0;
    overflow: auto;
    border: 1px solid var(--line);
    background: var(--surface);
    border-radius: 6px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.03);
  }}
  
  table {{
    border-collapse: separate;
    border-spacing: 0;
    width: 100%;
    min-width: 1100px;
    font-size: 13.5px;
    table-layout: fixed;
  }}
  
  /* Columns */
  col.col-rk {{ width: 56px; }}
  col.col-repo {{ width: 250px; }}
  col.col-track {{ width: 110px; }}
  col.col-growth {{ width: 115px; }}
  col.col-stars {{ width: 95px; }}
  col.col-created {{ width: 105px; }}
  col.col-what {{ width: 230px; }}
  col.col-use {{ width: auto; min-width: 240px; }}
  
  /* Table Header Stuck to Top of Viewport */
  thead th {{
    position: sticky;
    top: 0;
    background: var(--th-bg);
    color: var(--ink);
    text-align: left;
    font-family: var(--mono);
    font-size: 11px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    padding: 11px 14px;
    border-bottom: 2px solid var(--ink);
    white-space: nowrap;
    z-index: 10;
    box-shadow: 0 1px 0 var(--line);
  }}
  
  thead th.th-rk {{ text-align: right; }}
  thead th.th-num {{ text-align: right; }}
  thead th.th-track {{ text-align: center; }}
  thead th.th-created {{ text-align: center; }}
  thead th:last-child {{ padding-right: 28px; }}
  
  tbody td {{
    padding: 10px 14px;
    border-bottom: 1px solid var(--line-subtle);
    vertical-align: top;
    line-height: 1.5;
  }}
  tbody td:last-child {{ padding-right: 28px; }}
  
  tbody tr:nth-child(even) {{ background: var(--surface-alt); }}
  tbody tr:hover {{ background: var(--hover); }}
  
  .rk {{
    font-family: var(--mono);
    color: var(--muted);
    text-align: right;
    font-weight: 500;
  }}
  .repo {{
    font-family: var(--mono);
    font-size: 13px;
    word-break: break-all;
  }}
  .repo a {{
    color: var(--ink);
    text-decoration: none;
    border-bottom: 1px solid var(--accent);
    font-weight: 500;
    transition: color 0.15s;
  }}
  .repo a:hover {{ color: var(--accent); }}
  
  .td-track {{ text-align: center; }}
  .badge {{
    display: inline-block;
    font-size: 11px;
    padding: 2px 7px;
    border-radius: 4px;
    white-space: nowrap;
    font-weight: 500;
  }}
  .num {{
    font-family: var(--mono);
    text-align: right;
    white-space: nowrap;
  }}
  .growth {{
    color: var(--pos);
    font-weight: 600;
  }}
  .created-cell {{
    font-family: var(--mono);
    text-align: center;
    color: var(--muted);
    font-size: 12.5px;
  }}
  .what {{
    color: var(--ink);
    font-weight: 500;
    word-break: break-word;
  }}
  .use {{
    color: var(--muted);
    line-height: 1.5;
    word-break: break-word;
  }}
  
  .empty {{
    padding: 48px;
    text-align: center;
    color: var(--muted);
    font-family: var(--mono);
  }}
  
  /* Footer within scrollable table bottom */
  .table-footer-note {{
    padding: 16px 20px;
    color: var(--muted);
    font-size: 12px;
    line-height: 1.6;
    background: var(--surface-alt);
    border-top: 1px solid var(--line);
  }}
  .table-footer-note code {{
    font-family: var(--mono);
    background: #eae4d4;
    padding: 1px 4px;
    border-radius: 3px;
    color: var(--ink);
  }}
  
  @media(max-width: 900px) {{
    .app-container {{ padding: 12px 16px; }}
    .stats {{ grid-template-columns: 1fr; }}
    .stat {{ border-right: none; border-bottom: 1px solid var(--line); }}
    .stat:last-child {{ border-bottom: none; }}
  }}
</style>
</head>
<body>

<div class="app-container">
  <!-- Top Fixed Area: Masthead, Stats, Filters, Controls -->
  <div class="top-fixed-region">
    <header class="masthead">
      <div class="masthead-main">
        <div class="kicker">Weekly GitHub Star Growth · 开源星增周榜</div>
        <h1>GitHub Star 增长周榜</h1>
        <p class="sub">统计窗口 {RUN_DATE} ｜ 筛选近 90 天 Star 净增长 ≥ 3000 且创建于近 36 个月内的开源仓库。增长口径为「当前 star − 90 天前 star」。</p>
      </div>
    </header>

    <section class="stats">
      <div class="stat"><div class="n">{total_count}</div><div class="l">总项目数</div></div>
      <div class="stat ai"><div class="n">{ai_agent_count}</div><div class="l">AI Agent 赛道</div></div>
      <div class="stat"><div class="n">{ai_agent_pct}</div><div class="l">AI Agent 占比</div></div>
    </section>

    <div class="controls-panel">
      <div class="ctl-row">
        <div class="pills" id="pills"></div>
      </div>
      <div class="ctl-row">
        <label class="toggle" id="aiToggle"><span class="switch"></span><span>只看 AI Agent</span></label>
        <span class="field">排序
          <select id="sortField">
            <option value="default">默认（AI Agent 优先 · 增长降序）</option>
            <option value="growth">近三月增长</option>
            <option value="stars">当前 star</option>
            <option value="created">创建时间</option>
          </select>
          <button class="btn-dir" id="dirBtn">降序 ↓</button>
        </span>
        <span class="field">增长 ≥ <input type="number" id="thresh" min="0" placeholder="3000"></span>
        <input type="search" id="search" placeholder="搜索 owner/repo 或中文说明…">
      </div>
    </div>

    <div class="meta-bar">
      <span id="count">显示 {total_count} / {total_count} 个项目</span>
      <span>数据来源：GitHub API · 线性插值</span>
    </div>
  </div>

  <!-- Bottom Scrollable Table Viewport -->
  <div class="table-viewport">
    <table>
      <colgroup>
        <col class="col-rk">
        <col class="col-repo">
        <col class="col-track">
        <col class="col-growth">
        <col class="col-stars">
        <col class="col-created">
        <col class="col-what">
        <col class="col-use">
      </colgroup>
      <thead><tr>
        <th class="th-rk">排名</th>
        <th>项目</th>
        <th class="th-track">赛道</th>
        <th class="th-num">近三月增长</th>
        <th class="th-num">当前 star</th>
        <th class="th-created">创建时间</th>
        <th>是什么</th>
        <th>主要用途</th>
      </tr></thead>
      <tbody id="tbody"></tbody>
    </table>

    <div class="table-footer-note">
      <p><strong>方法说明：</strong>「近三月增长」= 当前 star − 90 天前 star（窗口截至 {RUN_DATE}）。当前 star 与创建时间取自 GitHub 官方 API（<code>api.github.com</code>）；90 天前 star 结合历史周榜多点插值及新建仓库基准得出。仅收录创建时间不早于 2023-08-31 的仓库；无法可靠核实增长数据的项目已严格剔除。</p>
    </div>
  </div>
</div>

<script>
const DATA = {data_json};

const TRACK_COLORS = {{
  "AI Agent": "#5e3a9b",
  "Coding Agent": "#2563eb",
  "模型/推理": "#d97706",
  "前端框架": "#db2777",
  "数据库": "#059669",
  "开发工具": "#4b5563",
  "基础设施": "#78350f",
  "音视频": "#ea580c",
  "多模态": "#0284c7",
  "机器人": "#475569"
}};

const state = {{ track:"全部", aiOnly:false, field:"default", dir:-1, thresh:0, q:"" }};

function fmt(n){{ return n.toLocaleString("en-US"); }}
function trackBadge(t){{
  const c = TRACK_COLORS[t] || "#4b5563";
  return `<span class="badge" style="background:${{c}}18;color:${{c}}">${{t}}</span>`;
}}
function passes(r){{
  if(state.aiOnly && r.track!=="AI Agent") return false;
  if(state.track!=="全部" && r.track!==state.track) return false;
  if(r.growth < state.thresh) return false;
  if(state.q){{
    const hay = (r.repo+" "+r.what+" "+r.use).toLowerCase();
    if(!hay.includes(state.q.toLowerCase())) return false;
  }}
  return true;
}}
function sortRows(rows){{
  const f = state.field;
  if(f==="default"){{
    return rows.slice().sort((a,b)=>{{
      const aiA = a.track==="AI Agent"?1:0, aiB = b.track==="AI Agent"?1:0;
      if(aiA!==aiB) return aiB-aiA;
      return b.growth - a.growth;
    }});
  }}
  let key;
  if(f==="growth") key=r=>r.growth;
  else if(f==="stars") key=r=>r.stars;
  else key=r=>r.created;
  return rows.slice().sort((a,b)=> state.dir<0 ? (key(b)>key(a)?1:-1) : (key(a)>key(b)?1:-1));
}}
function render(){{
  const rows = sortRows(DATA.filter(passes));
  const tb = document.getElementById("tbody");
  if(rows.length===0){{ tb.innerHTML = `<tr><td colspan="8" class="empty">没有符合条件的项目</td></tr>`; }}
  else {{
    tb.innerHTML = rows.map(r=>{{
      return `<tr>
        <td class="rk">${{r.rank}}</td>
        <td class="repo"><a href="${{r.url}}" target="_blank" rel="noopener">${{r.repo}}</a></td>
        <td class="td-track">${{trackBadge(r.track)}}</td>
        <td class="num growth">+${{fmt(r.growth)}}</td>
        <td class="num">${{fmt(r.stars)}}</td>
        <td class="created-cell">${{r.created}}</td>
        <td class="what">${{r.what}}</td>
        <td class="use">${{r.use}}</td>
      </tr>`;
    }}).join("");
  }}
  document.getElementById("count").textContent = `显示 ${{rows.length}} / ${{DATA.length}} 个项目`;
}}
function buildPills(){{
  const counts = {{}};
  DATA.forEach(r=> counts[r.track]=(counts[r.track]||0)+1);
  const order = ["全部", ...Object.keys(counts).sort((a,b)=>counts[b]-counts[a])];
  const box = document.getElementById("pills");
  box.innerHTML = order.map(t=>{{
    const c = t==="全部"?DATA.length:counts[t];
    return `<span class="pill${{t===state.track?' active':''}}" data-t="${{t}}">${{t}}<span class="c">${{c}}</span></span>`;
  }}).join("");
  box.querySelectorAll(".pill").forEach(p=>{{
    p.onclick=()=>{{ state.track=p.dataset.t; buildPills(); render(); }};
  }});
}}
document.getElementById("aiToggle").onclick=function(){{
  state.aiOnly=!state.aiOnly; this.classList.toggle("on",state.aiOnly); render();
}};
document.getElementById("sortField").onchange=function(){{ state.field=this.value; render(); }};
document.getElementById("dirBtn").onclick=function(){{
  state.dir*=-1; this.textContent = state.dir<0?"降序 ↓":"升序 ↑"; render();
}};
document.getElementById("thresh").oninput=function(){{ state.thresh=parseInt(this.value)||0; render(); }};
document.getElementById("search").oninput=function(){{ state.q=this.value.trim(); render(); }};

buildPills();
render();
</script>
</body>
</html>
"""

archive_html = os.path.join(TARGET_DIR, "archive", f"{RUN_DATE}.html")
index_html = os.path.join(TARGET_DIR, "index.html")

for cp in [csv_path, archive_csv]:
    with open(cp, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in final_list:
            writer.writerow({
                '排名': r['rank'],
                '项目': r['repo'],
                'GitHub链接': r['url'],
                '赛道': r['track'],
                '近三月增长': r['growth'],
                '当前star': r['stars'],
                '创建时间': r['created'],
                '是什么': r['what'],
                '主要用途': r['use']
            })

total_count = len(final_list)
ai_agent_count = len(ai_agent_repos)
ai_agent_pct = f"{(ai_agent_count / total_count * 100):.1f}%" if total_count > 0 else "0.0%"
data_json = json.dumps(final_list, ensure_ascii=False)

html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GitHub Star 增长周榜 · {RUN_DATE}</title>
<style>
  :root{{
    --paper:#f4f1ea; --surface:#fffdf8; --ink:#1b1a16; --muted:#76726a;
    --line:#e0dacb; --accent:#6a4ba3; --pos:#3f6b4f;
    --th-bg:#eae4d4;
    --serif:"Iowan Old Style","Apple Garamond","Palatino Linotype",Palatino,Georgia,serif;
    --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,"PingFang SC","Microsoft YaHei",sans-serif;
    --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
  }}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);
    font-size:15px;line-height:1.5;-webkit-font-smoothing:antialiased;padding:0 0 64px}}
  .wrap{{max-width:1240px;margin:0 auto;padding:0 24px}}
  header.masthead{{border-bottom:3px double var(--ink);padding:38px 0 22px;margin-bottom:8px}}
  .kicker{{font-family:var(--mono);font-size:12px;letter-spacing:.18em;text-transform:uppercase;color:var(--muted)}}
  h1{{font-family:var(--serif);font-weight:600;font-size:clamp(34px,6vw,58px);line-height:1.02;
    margin:6px 0 4px;letter-spacing:-.01em}}
  .sub{{color:var(--muted);max-width:70ch;font-size:14.5px;margin-top:8px}}
  .stats{{display:grid;grid-template-columns:repeat(3,1fr);gap:0;border:1px solid var(--line);
    background:var(--surface);margin:26px 0 22px}}
  .stat{{padding:20px 22px;border-right:1px solid var(--line)}}
  .stat:last-child{{border-right:none}}
  .stat .n{{font-family:var(--serif);font-size:clamp(30px,5vw,46px);font-weight:600;line-height:1}}
  .stat .l{{font-family:var(--mono);font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin-top:8px}}
  .stat.ai .n{{color:var(--accent)}}
  
  .controls{{position:sticky;top:0;z-index:30;background:var(--paper);
    padding:14px 0 12px;border-bottom:1px solid var(--line);margin-bottom:14px;
    box-shadow:0 4px 12px rgba(27,26,22,0.03)}}
  .ctl-row{{display:flex;flex-wrap:wrap;gap:10px 14px;align-items:center}}
  .pills{{display:flex;flex-wrap:wrap;gap:6px}}
  .pill{{font-family:var(--sans);font-size:13px;padding:6px 12px;border:1px solid var(--line);
    background:var(--surface);color:var(--ink);border-radius:999px;cursor:pointer;transition:.15s;white-space:nowrap}}
  .pill:hover{{border-color:var(--ink)}}
  .pill.active{{background:var(--ink);color:var(--paper);border-color:var(--ink)}}
  .pill .c{{font-family:var(--mono);font-size:11px;opacity:.6;margin-left:5px}}
  .toggle{{display:inline-flex;align-items:center;gap:8px;cursor:pointer;font-size:13px;user-select:none}}
  .switch{{width:38px;height:22px;border-radius:999px;background:var(--line);position:relative;transition:.2s;flex:none}}
  .switch::after{{content:"";position:absolute;top:2px;left:2px;width:18px;height:18px;border-radius:50%;background:var(--surface);transition:.2s;box-shadow:0 1px 2px rgba(0,0,0,.25)}}
  .toggle.on .switch{{background:var(--accent)}}
  .toggle.on .switch::after{{left:18px}}
  .field{{display:flex;align-items:center;gap:6px;font-size:13px;color:var(--muted)}}
  select,input[type=search],input[type=number]{{font-family:var(--sans);font-size:13px;padding:7px 10px;
    border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:8px;outline:none}}
  input[type=search]{{min-width:210px;flex:1;max-width:320px}}
  input[type=number]{{width:110px}}
  select:focus,input:focus{{border-color:var(--accent)}}
  .btn-dir{{font-family:var(--mono);font-size:12px;padding:7px 10px;border:1px solid var(--line);background:var(--surface);
    border-radius:8px;cursor:pointer;color:var(--ink)}}
  .btn-dir:hover{{border-color:var(--ink)}}
  .count{{font-family:var(--mono);font-size:12px;color:var(--muted);margin:4px 0 10px}}
  
  .tbl-wrap{{max-height:calc(100vh - 150px);min-height:400px;overflow:auto;border:1px solid var(--line);background:var(--surface);border-radius:4px;box-shadow:0 2px 8px rgba(0,0,0,0.02)}}
  table{{border-collapse:separate;border-spacing:0;width:100%;min-width:960px;font-size:13.5px}}
  thead th{{position:sticky;top:0;background:var(--th-bg);color:var(--ink);text-align:left;
    font-family:var(--mono);font-size:11px;letter-spacing:.06em;text-transform:uppercase;
    padding:12px 14px;border-bottom:2px solid var(--ink);white-space:nowrap;z-index:10;
    box-shadow:0 1px 0 var(--line)}}
  tbody td{{padding:11px 14px;border-bottom:1px solid var(--line);vertical-align:top}}
  tbody tr:nth-child(even){{background:#faf7f0}}
  tbody tr:hover{{background:#f1ece0}}
  .rk{{font-family:var(--mono);color:var(--muted);text-align:right;width:48px}}
  .repo{{font-family:var(--mono);font-size:13px;white-space:nowrap}}
  .repo a{{color:var(--ink);text-decoration:none;border-bottom:1px solid var(--accent);font-weight:500}}
  .repo a:hover{{color:var(--accent)}}
  .badge{{display:inline-block;font-size:11.5px;padding:3px 9px;border-radius:6px;white-space:nowrap;font-weight:500}}
  .num{{font-family:var(--mono);text-align:right;white-space:nowrap}}
  .growth{{color:var(--pos);font-weight:600}}
  .what{{color:var(--ink);font-weight:500;min-width:190px}}
  .use{{color:var(--muted);max-width:42ch;line-height:1.45}}
  footer{{margin-top:28px;color:var(--muted);font-size:12.5px;line-height:1.7;border-top:1px solid var(--line);padding-top:16px}}
  footer code{{font-family:var(--mono);background:#ece7da;padding:1px 5px;border-radius:4px}}
  .empty{{padding:40px;text-align:center;color:var(--muted);font-family:var(--mono)}}
  @media(max-width:680px){{
    .stats{{grid-template-columns:1fr}}
    .stat{{border-right:none;border-bottom:1px solid var(--line)}}
    .stat:last-child{{border-bottom:none}}
    .tbl-wrap{{max-height:calc(100vh - 200px)}}
  }}
</style>
</head>
<body>
<div class="wrap">
  <header class="masthead">
    <div class="kicker">Weekly GitHub Star Growth · 开源星增周榜</div>
    <h1>GitHub Star 增长周榜</h1>
    <p class="sub">统计窗口 {RUN_DATE} ｜ 筛选「近三个月 star 净增长 ≥ 3000」且创建于近 36 个月内的公开仓库。
    增长口径为「当前 star − 90 天前 star」；当前 star 与创建时间取自 GitHub 官方 API，90 天前 star 结合历史周榜数据与线性插值得出。</p>
  </header>

  <section class="stats">
    <div class="stat"><div class="n">{total_count}</div><div class="l">总项目数</div></div>
    <div class="stat ai"><div class="n">{ai_agent_count}</div><div class="l">AI Agent 赛道</div></div>
    <div class="stat"><div class="n">{ai_agent_pct}</div><div class="l">AI Agent 占比</div></div>
  </section>

  <div class="controls">
    <div class="ctl-row">
      <div class="pills" id="pills"></div>
    </div>
    <div class="ctl-row" style="margin-top:10px">
      <label class="toggle" id="aiToggle"><span class="switch"></span><span>只看 AI Agent</span></label>
      <span class="field">排序
        <select id="sortField">
          <option value="default">默认（AI Agent 优先 · 增长降序）</option>
          <option value="growth">近三月增长</option>
          <option value="stars">当前 star</option>
          <option value="created">创建时间</option>
        </select>
        <button class="btn-dir" id="dirBtn">降序 ↓</button>
      </span>
      <span class="field">增长 ≥ <input type="number" id="thresh" min="0" placeholder="3000"></span>
      <input type="search" id="search" placeholder="搜索 owner/repo 或中文说明…">
    </div>
  </div>
  <div class="count" id="count"></div>

  <div class="tbl-wrap">
    <table>
      <thead><tr>
        <th>排名</th><th>项目</th><th>赛道</th><th>近三月增长</th>
        <th>当前 star</th><th>创建时间</th><th>是什么</th><th>主要用途</th>
      </tr></thead>
      <tbody id="tbody"></tbody>
    </table>
  </div>

  <footer>
    <p><strong>方法说明：</strong>「近三月增长」= 当前 star − 90 天前 star（窗口截至 {RUN_DATE}，即 90 天内的净增）。
    当前 star 与创建时间来自 GitHub 官方仓库页 / API（<code>api.github.com</code>）；
    90 天前 star 结合历史周榜多点插值及新建仓库基准得出。
    仅收录创建时间不早于近 36 个月的仓库；无法可靠核实增长数据的项目已严格剔除。</p>
    <p>生成日期 {RUN_DATE} ｜ 共 {total_count} 个仓库 ｜ 数据来源：GitHub API · 周榜数据中心。</p>
  </footer>
</div>

<script>
const DATA = {data_json};

const TRACK_COLORS = {{
  "AI Agent": "#6a4ba3",
  "Coding Agent": "#2f6f8f",
  "模型/推理": "#b5651d",
  "前端框架": "#c0567a",
  "数据库": "#3f7d5a",
  "开发工具": "#6b7280",
  "基础设施": "#7a6a4f",
  "音视频": "#b0543f",
  "多模态": "#4a7ca5",
  "机器人": "#5a5a5a"
}};

const state = {{ track:"全部", aiOnly:false, field:"default", dir:-1, thresh:0, q:"" }};

function fmt(n){{ return n.toLocaleString("en-US"); }}
function trackBadge(t){{
  const c = TRACK_COLORS[t] || "#6b7280";
  return `<span class="badge" style="background:${{c}}22;color:${{c}}">${{t}}</span>`;
}}
function passes(r){{
  if(state.aiOnly && r.track!=="AI Agent") return false;
  if(state.track!=="全部" && r.track!==state.track) return false;
  if(r.growth < state.thresh) return false;
  if(state.q){{
    const hay = (r.repo+" "+r.what+" "+r.use).toLowerCase();
    if(!hay.includes(state.q.toLowerCase())) return false;
  }}
  return true;
}}
function sortRows(rows){{
  const f = state.field;
  if(f==="default"){{
    return rows.slice().sort((a,b)=>{{
      const aiA = a.track==="AI Agent"?1:0, aiB = b.track==="AI Agent"?1:0;
      if(aiA!==aiB) return aiB-aiA;
      return b.growth - a.growth;
    }});
  }}
  let key;
  if(f==="growth") key=r=>r.growth;
  else if(f==="stars") key=r=>r.stars;
  else key=r=>r.created;
  return rows.slice().sort((a,b)=> state.dir<0 ? (key(b)>key(a)?1:-1) : (key(a)>key(b)?1:-1));
}}
function render(){{
  const rows = sortRows(DATA.filter(passes));
  const tb = document.getElementById("tbody");
  if(rows.length===0){{ tb.innerHTML = `<tr><td colspan="8" class="empty">没有符合条件的项目</td></tr>`; }}
  else {{
    tb.innerHTML = rows.map(r=>{{
      return `<tr>
        <td class="rk">${{r.rank}}</td>
        <td class="repo"><a href="${{r.url}}" target="_blank" rel="noopener">${{r.repo}}</a></td>
        <td>${{trackBadge(r.track)}}</td>
        <td class="num growth">+${{fmt(r.growth)}}</td>
        <td class="num">${{fmt(r.stars)}}</td>
        <td class="num">${{r.created}}</td>
        <td class="what">${{r.what}}</td>
        <td class="use">${{r.use}}</td>
      </tr>`;
    }}).join("");
  }}
  document.getElementById("count").textContent = `显示 ${{rows.length}} / ${{DATA.length}} 个项目`;
}}
function buildPills(){{
  const counts = {{}};
  DATA.forEach(r=> counts[r.track]=(counts[r.track]||0)+1);
  const order = ["全部", ...Object.keys(counts).sort((a,b)=>counts[b]-counts[a])];
  const box = document.getElementById("pills");
  box.innerHTML = order.map(t=>{{
    const c = t==="全部"?DATA.length:counts[t];
    return `<span class="pill${{t===state.track?' active':''}}" data-t="${{t}}">${{t}}<span class="c">${{c}}</span></span>`;
  }}).join("");
  box.querySelectorAll(".pill").forEach(p=>{{
    p.onclick=()=>{{ state.track=p.dataset.t; buildPills(); render(); }};
  }});
}}
document.getElementById("aiToggle").onclick=function(){{
  state.aiOnly=!state.aiOnly; this.classList.toggle("on",state.aiOnly); render();
}};
document.getElementById("sortField").onchange=function(){{ state.field=this.value; render(); }};
document.getElementById("dirBtn").onclick=function(){{
  state.dir*=-1; this.textContent = state.dir<0?"降序 ↓":"升序 ↑"; render();
}};
document.getElementById("thresh").oninput=function(){{ state.thresh=parseInt(this.value)||0; render(); }};
document.getElementById("search").oninput=function(){{ state.q=this.value.trim(); render(); }};

buildPills();
render();
</script>
</body>
</html>
"""

for hp in [html_path, archive_html, index_html]:
    with open(hp, 'w', encoding='utf-8') as f:
        f.write(html_content)

print(f"Successfully generated CSV & HTML files for {RUN_DATE}!")

# Git commit and push
try:
    subprocess.run(['git', 'add', '-A'], cwd=TARGET_DIR, check=True)
    subprocess.run(['git', 'commit', '-m', f"feat(ranking): automated weekly star growth update ({RUN_DATE})"], cwd=TARGET_DIR)
    subprocess.run(['git', 'push', 'origin', 'main'], cwd=TARGET_DIR, check=True)
    print("Git repository pushed successfully.")
except Exception as e:
    print(f"Git push warning: {e}")

# Open in Chrome
try:
    subprocess.run(['open', '-a', 'Google Chrome', html_path])
    print("Opened in Google Chrome.")
except Exception as e:
    print(f"Open Chrome warning: {e}")
