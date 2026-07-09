import os
import urllib.request
import urllib.parse
import json
import xml.etree.ElementTree as ET
import yaml
from datetime import datetime
from google import genai

# 1. 加载本地过滤配置文件
with open('config.yaml', 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

# 2. 从 arXiv 检索最新的预取论文
print("🚀 正在从 arXiv 实时抓取最新的预取领域文献...")
raw_query = config['search_queries'][0]
encoded_query = urllib.parse.quote(raw_query)
url = f'http://export.arxiv.org/api/query?search_query={encoded_query}&max_results=30&sortBy=submittedDate&sortOrder=descending'

try:
    response = urllib.request.urlopen(url)
    xml_data = response.read()
    root = ET.fromstring(xml_data)
except Exception as e:
    print(f"❌ 请求 arXiv API 失败: {e}")
    exit(1)

new_papers = []
for entry in root.findall('{http://www.w3.org/2005/Atom}entry'):
    title = entry.find('{http://www.w3.org/2005/Atom}title').text.strip().replace('\n', ' ')
    summary = entry.find('{http://www.w3.org/2005/Atom}summary').text.strip().replace('\n', ' ')
    paper_url = entry.find('{http://www.w3.org/2005/Atom}id').text
    
    published_raw = entry.find('{http://www.w3.org/2005/Atom}published').text
    try:
        dt = datetime.strptime(published_raw, "%Y-%m-%dT%H:%M:%SZ")
        published_date = dt.strftime("%Y-%m-%d")
    except:
        published_date = published_raw[:10]
        
    new_papers.append({'title': title, 'summary': summary, 'url': paper_url, 'date': published_date})

# 3. 硬件预取规则过滤
filtered_new_papers = []
for p in new_papers:
    text_to_check = (p['title'] + " " + p['summary']).lower()
    has_include = any(word in text_to_check for word in config['filter_rules']['include'])
    has_exclude = any(word in text_to_check for word in config['filter_rules']['exclude'])
    if has_include and not has_exclude:
        filtered_new_papers.append(p)

print(f"📊 今日全网捕获并清洗出 {len(filtered_new_papers)} 篇最新的核心架构论文。")

# 4. 【核心升级：增量数据合并与去重】防止没有新论文时网页变空
database_file = "paper_database.json"
historical_data = []

if os.path.exists(database_file):
    try:
        with open(database_file, "r", encoding="utf-8") as f:
            historical_data = json.load(f)
    except:
        historical_data = []

# 以 URL 作为唯一钥匙进行去重合并
existing_urls = {p['url'] for p in historical_data}
api_key = os.getenv("LLM_API_KEY")

if filtered_new_papers and api_key:
    client = genai.Client(api_key=api_key)
    TOP_VENUES = ["isca", "micro", "hpca", "asplos", "ieee tc", "taco", "cal", "sigmetrics"]
    
    for paper in filtered_new_papers:
        if paper['url'] in existing_urls:
            continue  # 如果这篇论文之前已经处理过了，直接跳过，拒绝重复消费Gemini额度
            
        print(f"🧪 正在深度处理新论文: {paper['title']}")
        
        # A. 真正请求 Semantic Scholar API 逆向识别顶会/权威期刊
        venue_info = "📦 arXiv 预印本"
        is_top = False
        try:
            arxiv_id = paper['url'].split('/abs/')[-1].split('v')[0]
            s2_url = f"https://api.semanticscholar.org/graph/v1/paper/arXiv:{arxiv_id}?fields=venue,publicationVenue"
            s2_req = urllib.request.Request(s2_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(s2_req, timeout=5) as s2_res:
                s2_data = json.loads(s2_res.read().decode())
                raw_venue = s2_data.get('venue', '')
                if not raw_venue and s2_data.get('publicationVenue'):
                    raw_venue = s2_data['publicationVenue'].get('name', '')
                
                if raw_venue:
                    matched = next((v for v in TOP_VENUES if v in raw_venue.lower()), None)
                    if matched:
                        venue_info = f"👑 顶会/权威认证: {raw_venue.upper()}"
                        is_top = True
                    else:
                        venue_info = f"📝 已发表至: {raw_venue}"
        except Exception as e:
            print(f"⚠️ 溯源失败({e})，默认保持预印本状态")

        # B. 真正请求 Gemini 2.5 Flash 输出真实、客观、高学术水准的中文同行评审意见
        prompt = (
            f"你是一个精通计算机体系结构、微架构（Microarchitecture）和存储子系统（Memory Subsystem）的顶级科学家。\n"
            f"请认真阅读以下硬件预取相关论文的标题和摘要，为其撰写一条真实、客观、严谨且高屋建瓴的【专家解读】。\n"
            f"要求用中文，分为两部分回答（总字数控制在150字以内）：\n"
            f"1. 核心创新：阐明其相较于传统预取器（如 Stride, SPP 等）在微架构设计或算法上的核心突破点。\n"
            f"2. 潜在价值：分析该方法对缓解存储墙（Memory Wall）或提升特定负载（如图计算、大模型推理）的实际工业价值。\n\n"
            f"标题: {paper['title']}\n"
            f"摘要: {paper['summary']}"
        )
        
        try:
            response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
            gemini_review = response.text.strip().replace('\n', '<br>')
        except Exception as e:
            gemini_review = f"Gemini 实时解读生成失败: {e}"
        
        # 组装成标准存储对象
        paper['venue'] = venue_info
        paper['is_top'] = is_top
        paper['review'] = gemini_review
        
        # 塞入历史数据库首位（保证按时间最新排序）
        historical_data.insert(0, paper)

# 只保留最近展示的 30 篇核心论文，防止静态网页过大
historical_data = historical_data[:30]

# 将更新后的数据写回本地“记忆库”
with open(database_file, "w", encoding="utf-8") as f:
    json.dump(historical_data, f, ensure_ascii=False, indent=2)

# 5. 渲染高颜值 HTML 静态主页
html_cards = ""
for idx, p in enumerate(historical_data):
    badge_class = "badge-top" if p.get('is_top', False) else ("badge-normal" if "已发表" in p.get('venue','') else "badge-arxiv")
    html_cards += f"""
    <div class="card">
        <div class="card-header-flow">
            <div class="card-tag">文献 {idx+1}</div>
            <span class="badge {badge_class}">{p.get('venue', '📦 arXiv 预印本')}</span>
        </div>
        <h2 class="card-title">{p['title']}</h2>
        <div class="card-meta">
            <span>📅 抓取/发表时间: <strong>{p['date']}</strong></span>
            <span>🔗 <a href="{p['url']}" target="_blank">查看 arXiv 官方原文</a></span>
        </div>
        <div class="card-analysis">
            <h3>🔬 Gemini 真实学术解读：</h3>
            <p>{p.get('review', '暂无解读')}</p>
        </div>
    </div>
    """

if not html_cards:
    html_cards = "<p style='text-align:center; color:#64748b;'>科研雷达正在全网搜索中，暂无匹配文献。</p>"

update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>处理器预取算法文献追踪大屏</title>
    <style>
        :root {{ --bg: #f8fafc; --text: #1e293b; --primary: #2563eb; --card-bg: #ffffff; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background-color: var(--bg); color: var(--text); margin: 0; padding: 0; line-height: 1.6; }}
        .header {{ background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 100%); color: white; text-align: center; padding: 45px 20px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); }}
        .header h1 {{ margin: 0; font-size: 2.2rem; font-weight: 800; letter-spacing: -0.05em; }}
        .header p {{ margin: 10px 0 0 0; opacity: 0.9; font-size: 1rem; }}
        .container {{ max-width: 900px; margin: 30px auto; padding: 0 20px; }}
        .card {{ background: var(--card-bg); border-radius: 16px; padding: 28px; margin-bottom: 25px; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.05); border: 1px solid #e2e8f0; transition: transform 0.2s; }}
        .card:hover {{ transform: translateY(-2px); box-shadow: 0 20px 25px -5px rgba(0,0,0,0.1); }}
        .card-header-flow {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }}
        .card-tag {{ display: inline-block; background: #f1f5f9; color: #475569; font-weight: 700; padding: 4px 12px; border-radius: 9999px; font-size: 0.85rem; }}
        .badge {{ padding: 6px 14px; border-radius: 9999px; font-size: 0.85rem; font-weight: 700; box-shadow: 0 2px 4px rgba(0,0,0,0.02); }}
        .badge-top {{ background: #fef3c7; color: #92400e; border: 1px solid #fde68a; }}
        .badge-normal {{ background: #e0f2fe; color: #0369a1; border: 1px solid #bae6fd; }}
        .badge-arxiv {{ background: #f1f5f9; color: #64748b; border: 1px solid #e2e8f0; }}
        .card-title {{ font-size: 1.4rem; margin: 0 0 15px 0; font-weight: 700; color: #0f172a; line-height: 1.3; }}
        .card-meta {{ font-size: 0.9rem; color: #64748b; margin-bottom: 20px; display: flex; gap: 20px; border-bottom: 1px solid #f1f5f9; padding-bottom: 12px; }}
        .card-meta a {{ color: var(--primary); text-decoration: none; font-weight: 600; }}
        .card-meta a:hover {{ text-decoration: underline; }}
        .card-analysis {{ background: #f0fdf4; border-left: 4px solid #22c55e; padding: 18px 20px; border-radius: 0 12px 12px 0; }}
        .card-analysis h3 {{ margin: 0 0 8px 0; font-size: 1.05rem; color: #166534; font-weight: 700; }}
        .card-analysis p {{ margin: 0; color: #14532d; font-size: 0.98rem; text-align: justify; }}
        footer {{ text-align: center; padding: 40px; color: #94a3b8; font-size: 0.85rem; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🚀 处理器预取算法文献追踪面板</h1>
        <p>集成 Semantic Scholar 顶会实时溯源与 Google Gemini 2.5 真实客观评审</p>
        <p style="font-size: 0.85rem; margin-top: 15px; opacity: 0.7;">🔄 大屏同步更新时间：{update_time} (北京时间)</p>
    </div>
    <div class="container">
        {html_cards}
    </div>
    <footer>
        <p>© 2026 Prefetch Paper Agent | 借鉴顶级学术智库标准构建</p>
    </footer>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_content)
print("🎯 生产级自动化网页与记忆图谱更新成功！")
