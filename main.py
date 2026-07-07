import os
import urllib.request
import urllib.parse
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
url = f'http://export.arxiv.org/api/query?search_query={encoded_query}&max_results=20&sortBy=submittedDate&sortOrder=descending'

try:
    response = urllib.request.urlopen(url)
    xml_data = response.read()
    root = ET.fromstring(xml_data)
except Exception as e:
    print(f"❌ 请求 arXiv API 失败: {e}")
    exit(1)

papers = []
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
        
    papers.append({'title': title, 'summary': summary, 'url': paper_url, 'date': published_date})

# 3. 硬件预取规则过滤
filtered_papers = []
for p in papers:
    text_to_check = (p['title'] + " " + p['summary']).lower()
    has_include = any(word in text_to_check for word in config['filter_rules']['include'])
    has_exclude = any(word in text_to_check for word in config['filter_rules']['exclude'])
    if has_include and not has_exclude:
        filtered_papers.append(p)

print(f"📊 过滤完成，剩余 {len(filtered_papers)} 篇核心架构论文。")

# 4. 调用 Gemini 生成技术总结并构建 HTML 网页
api_key = os.getenv("LLM_API_KEY")
html_cards = ""

if filtered_papers and api_key:
    client = genai.Client(api_key=api_key)
    
    for idx, paper in enumerate(filtered_papers):
        prompt = (
            f"你是一个精通计算机体系结构（Computer Architecture）的专家。\n"
            f"请用两句话将下面这篇硬件预取算法论文的【核心创新点】和【实验效果】翻译并提炼为通俗易懂的中文：\n\n"
            f"标题: {paper['title']}\n"
            f"摘要: {paper['summary']}"
        )
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
            )
            gemini_review = response.text.strip().replace('\n', '<br>')
        except Exception as e:
            gemini_review = f"<span style='color:red;'>Gemini 总结失败: {e}</span>"
            
        # 动态拼接精美的网页卡片 (借鉴一流前端设计规范)
        html_cards += f"""
        <div class="card">
            <div class="card-tag">论文 {idx+1}</div>
            <h2 class="card-title">{paper['title']}</h2>
            <div class="card-meta">
                <span>📅 发表时间: <strong>{paper['date']}</strong></span>
                <span>🔗 <a href="{paper['url']}" target="_blank">查看 arXiv 原文</a></span>
            </div>
            <div class="card-analysis">
                <h3>💡 Gemini 专家解读：</h3>
                <p>{gemini_review}</p>
            </div>
        </div>
        """
else:
    html_cards = "<p style='text-align:center; color:#64748b;'>今日暂无符合硬件预取标准的最新论文更新。</p>"

# 5. 构筑一流水准的 HTML 页面模板 (自带高端渐变色与优雅卡片流布局)
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
        .header {{ background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%); color: white; text-align: center; padding: 40px 20px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); }}
        .header h1 {{ margin: 0; font-size: 2.2rem; font-weight: 800; letter-spacing: -0.05em; }}
        .header p {{ margin: 10px 0 0 0; opacity: 0.9; font-size: 1rem; }}
        .container {{ max-width: 900px; margin: 30px auto; padding: 0 20px; }}
        .card {{ background: var(--card-bg); border-radius: 16px; padding: 28px; margin-bottom: 25px; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.05); border: 1px solid #e2e8f0; transition: transform 0.2s; }}
        .card:hover {{ transform: translateY(-2px); box-shadow: 0 20px 25px -5px rgba(0,0,0,0.1); }}
        .card-tag {{ display: inline-block; background: #dbeafe; color: #1e40af; font-weight: 700; padding: 4px 12px; border-radius: 9999px; font-size: 0.85rem; margin-bottom: 12px; }}
        .card-title {{ font-size: 1.4rem; margin: 0 0 15px 0; font-weight: 700; color: #0f172a; line-height: 1.3; }}
        .card-meta {{ font-size: 0.9rem; color: #64748b; margin-bottom: 20px; display: flex; gap: 20px; border-bottom: 1px solid #f1f5f9; padding-bottom: 12px; }}
        .card-meta a {{ color: var(--primary); text-decoration: none; font-weight: 600; }}
        .card-meta a:hover {{ text-decoration: underline; }}
        .card-analysis {{ background: #f0fdf4; border-left: 4px solid #22c55e; padding: 15px 20px; border-radius: 0 12px 12px 0; }}
        .card-analysis h3 {{ margin: 0 0 8px 0; font-size: 1.05rem; color: #166534; font-weight: 700; }}
        .card-analysis p {{ margin: 0; color: #14532d; font-size: 1rem; }}
        footer {{ text-align: center; padding: 30px; color: #94a3b8; font-size: 0.85rem; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🚀 处理器预取算法文献追踪面板</h1>
        <p>基于开源规则引擎与 Google Gemini 2.5 Flash 强力驱动</p>
        <p style="font-size: 0.85rem; margin-top: 15px; opacity: 0.7;">🔄 智能生成时间：{update_time} (北京时间)</p>
    </div>
    <div class="container">
        {html_cards}
    </div>
    <footer>
        <p>© 2026 Prefetch Paper Agent | 借鉴世界一流学术追踪标准构建</p>
    </footer>
</body>
</html>
"""

# 保存网页到项目根目录下，命名为 index.html
with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_content)
print("🎯 炫酷网页版 HTML 生成成功！文件已写入本地目录。")
