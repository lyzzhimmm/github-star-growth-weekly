#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import csv
import json
from io import StringIO

from weekly_common import (
    CREATED_MONTHS,
    HISTORY_TOLERANCE_DAYS,
    MIN_GROWTH,
    RUN_DATE,
    WINDOW_DAYS,
)


def generate_csv(rows: list[dict]) -> str:
    fieldnames = ["排名", "项目", "GitHub链接", "赛道", "近三月增长", "当前star", "创建时间", "是什么", "主要用途"]
    buf = StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for r in rows:
        writer.writerow({
            "排名": r["rank"],
            "项目": r["repo"],
            "GitHub链接": r["url"],
            "赛道": r["track"],
            "近三月增长": r["growth"],
            "当前star": r["stars"],
            "创建时间": r["created"],
            "是什么": r["what"],
            "主要用途": r["use"],
        })
    return "\ufeff" + buf.getvalue()


def generate_html(rows: list[dict], excluded_unverified: int) -> str:
    total = len(rows)
    ai_count = sum(1 for r in rows if r["track"] == "AI Agent")
    ai_pct = (ai_count / total * 100) if total else 0
    data_json = json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")

    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GitHub Star 增长周榜 · {RUN_DATE}</title>
<style>
:root{{--bg:#f5f2ea;--card:#fffdf8;--ink:#1d1c19;--muted:#706c64;--line:#ddd7c9;--accent:#65429b;--green:#2f6b4f}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}}
.wrap{{max-width:1320px;margin:auto;padding:28px 22px 64px}}h1{{font:600 clamp(34px,6vw,58px)/1.05 Georgia,"Songti SC",serif;margin:6px 0}}
.kicker{{font:12px ui-monospace,monospace;letter-spacing:.14em;color:var(--muted)}}.sub{{color:var(--muted);max-width:900px}}
.stats{{display:grid;grid-template-columns:repeat(3,1fr);margin:22px 0;background:var(--card);border:1px solid var(--line)}}.stat{{padding:18px 20px;border-right:1px solid var(--line)}}.stat:last-child{{border:0}}.n{{font:600 36px Georgia,serif}}.l{{color:var(--muted);font-size:12px}}
.controls{{position:sticky;top:0;z-index:5;background:rgba(245,242,234,.96);backdrop-filter:blur(8px);padding:12px 0;border-bottom:1px solid var(--line)}}.row{{display:flex;gap:9px;flex-wrap:wrap;align-items:center}}
button,select,input{{font:inherit;border:1px solid var(--line);background:var(--card);padding:7px 10px;border-radius:8px;color:var(--ink)}}button{{cursor:pointer}}button.active{{background:var(--ink);color:white}}
input[type=search]{{min-width:260px;flex:1}}input[type=number]{{width:110px}}.table{{margin-top:14px;overflow:auto;max-height:70vh;background:var(--card);border:1px solid var(--line)}}
table{{border-collapse:separate;border-spacing:0;min-width:1120px;width:100%}}th{{position:sticky;top:0;background:#ebe5d7;text-align:left;font:11px ui-monospace,monospace;padding:11px;border-bottom:2px solid var(--ink)}}
td{{padding:10px 11px;border-bottom:1px solid #ece6d8;vertical-align:top}}tr:nth-child(even) td{{background:#faf7f0}}a{{color:var(--ink);text-decoration-color:var(--accent)}}.num{{font-family:ui-monospace,monospace;text-align:right;white-space:nowrap}}.growth{{color:var(--green);font-weight:700}}
.badge{{display:inline-block;padding:2px 8px;border:1px solid var(--line);border-radius:999px;white-space:nowrap}}footer{{color:var(--muted);margin-top:24px;border-top:1px solid var(--line);padding-top:15px}}
@media(max-width:700px){{.stats{{grid-template-columns:1fr}}.stat{{border-right:0;border-bottom:1px solid var(--line)}}}}
</style></head><body><div class="wrap">
<div class="kicker">WEEKLY GITHUB STAR GROWTH</div><h1>GitHub Star 增长周榜</h1>
<div class="sub">统计日 {RUN_DATE} · 最近 {WINDOW_DAYS} 天增长 ≥ {MIN_GROWTH} · 仅保留近 {CREATED_MONTHS} 个月创建的公开仓库。旧仓库增长只接受 OSSInsight 离散历史快照差值；不做线性插值或按仓库年龄估算。</div>
<section class="stats"><div class="stat"><div class="n">{total}</div><div class="l">总项目数</div></div><div class="stat"><div class="n">{ai_count}</div><div class="l">AI Agent</div></div><div class="stat"><div class="n">{ai_pct:.1f}%</div><div class="l">AI Agent 占比</div></div></section>
<div class="controls"><div class="row"><select id="track"><option value="">全部赛道</option></select><button id="ai">只看 AI Agent</button>
<select id="sort"><option value="default">默认排序</option><option value="growth">近三月增长</option><option value="stars">当前 star</option><option value="created">创建时间</option></select>
<button id="dir">降序 ↓</button><input id="min" type="number" min="0" value="{MIN_GROWTH}" aria-label="最小增长"><input id="q" type="search" placeholder="搜索 owner/repo 或说明"></div></div>
<div id="count" style="margin:10px 0;color:var(--muted)"></div><div class="table"><table><thead><tr><th>#</th><th>项目</th><th>赛道</th><th>近三月增长</th><th>当前 star</th><th>创建时间</th><th>是什么</th><th>主要用途</th></tr></thead><tbody id="body"></tbody></table></div>
<footer>数据口径：当前 star / created_at 来自 GitHub。窗口内新仓库因目标日尚不存在，历史 star 精确记 0。窗口前已存在的仓库使用 OSSInsight stargazers history 的离散日快照，目标日只接受最近 ±{HISTORY_TOLERANCE_DAYS} 天快照，不进行插值。增长按同一 OSSInsight 序列的“最新累计值 − 目标日累计值”计算。因历史数据不可用或无法在容差内找到可靠快照而排除 {excluded_unverified} 个候选。OSSInsight 数据可能存在覆盖延迟，因此榜单坚持宁缺毋滥。</footer>
</div><script>
const DATA={data_json};const track=document.getElementById('track'),body=document.getElementById('body'),q=document.getElementById('q'),min=document.getElementById('min'),sort=document.getElementById('sort'),dir=document.getElementById('dir'),ai=document.getElementById('ai'),count=document.getElementById('count');let onlyAI=false,desc=true;
[...new Set(DATA.map(x=>x.track))].sort().forEach(t=>{{const o=document.createElement('option');o.value=t;o.textContent=t;track.appendChild(o)}});
function esc(s){{return String(s).replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]))}}
function render(){{const needle=q.value.trim().toLowerCase(),threshold=Number(min.value||0);let a=DATA.filter(x=>(!track.value||x.track===track.value)&&(!onlyAI||x.track==='AI Agent')&&x.growth>=threshold&&(!needle||(`${{x.repo}} ${{x.what}} ${{x.use}}`).toLowerCase().includes(needle)));const field=sort.value;if(field==='default')a.sort((x,y)=>x.track==='AI Agent'&&y.track!=='AI Agent'?-1:y.track==='AI Agent'&&x.track!=='AI Agent'?1:y.growth-x.growth);else a.sort((x,y)=>{{let A=x[field],B=y[field];if(field==='created'){{A=Date.parse(A);B=Date.parse(B)}}return(A>B?1:A<B?-1:0)*(desc?-1:1)}});body.innerHTML=a.map((x,i)=>`<tr><td class="num">${{i+1}}</td><td><a href="${{esc(x.url)}}" target="_blank" rel="noopener">${{esc(x.repo)}}</a></td><td><span class="badge">${{esc(x.track)}}</span></td><td class="num growth">+${{x.growth.toLocaleString()}}</td><td class="num">${{x.stars.toLocaleString()}}</td><td>${{esc(x.created)}}</td><td>${{esc(x.what)}}</td><td>${{esc(x.use)}}</td></tr>`).join('');count.textContent=`显示 ${{a.length}} / ${{DATA.length}} 个项目`;}}
[track,q,min,sort].forEach(el=>el.addEventListener('input',render));ai.addEventListener('click',()=>{{onlyAI=!onlyAI;ai.classList.toggle('active',onlyAI);render()}});dir.addEventListener('click',()=>{{desc=!desc;dir.textContent=desc?'降序 ↓':'升序 ↑';render()}});render();
</script></body></html>'''
