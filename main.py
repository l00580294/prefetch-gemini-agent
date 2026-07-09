import os
import urllib.request
import urllib.parse
import json
import xml.etree.ElementTree as ET
import yaml
import time
from datetime import datetime

# ==========================================
# 【工业级请求：带硬超时的底层网络连接器】
# ==========================================
def robust_http_request(url, headers=None, data=None, max_retries=3):
    if headers is None:
        headers = {'User-Agent': 'Mozilla/5.0'}
    
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=headers, data=data)
            # 严格限制连接超时 10 秒，防止被第三方平台恶意挂起（Hang住）
            with urllib.request.urlopen(req, timeout=10) as response:
                content = response.read(1024 * 1024 * 3) # 最大3MB限制
                if content:
                    return content
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"❌ 网络请求彻底失败 (已尝试 {max_retries} 次): 错误: {e}")
                return None
            sleep_time = 2 ** attempt
            time.sleep(sleep_time)
    return None

# ==========================================
# 【核心升级：直连 Google 官方原生 AI Studio 引擎】
# ==========================================
def ask_gemini_native(prompt, api_key):
    # 使用 Google 官方原生底层 REST API 端口（gemini-2.5-flash 官方标准终点）
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 300
        }
    }
    data = json.dumps(payload).encode('utf-8')
    
    res_bytes = robust_http_request(url, headers=headers, data=data)
    if res_bytes:
        try:
            res_json = json.loads(res_bytes.decode('utf-8'))
            # 解析 Google 官方标准的 JSON 响应树
            content = res_json['candidates'][0]['content']['parts'][0]['text'].strip()
            return content
        except Exception as e:
            print(f"⚠️ 官方原生通道响应解析失败: {e}")
    return None

# ==========================================
# 主运行核心逻辑
# ==========================================
def main():
    with open('config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    config_months = config.get('time_window', {}).get('months', 6)
    print(f"📅 时间窗口裁剪器：仅检索过去 {config_months} 个月内发表的新论文。")

    # 缩小初筛池至 50 篇，既减轻 arXiv 压力，又能完美覆盖近半年的核心论文
    print("🚀 正在从 arXiv 实时海选原始文献...")
    raw_query = config['search_queries'][0]
    encoded_query = urllib.parse.quote(raw_query)
    arxiv_url = f'http://export.arxiv.org/api/query?search_query={encoded_query}&max_results=50&sortBy=submittedDate&sortOrder=descending'

    xml_data = robust_http_request(arxiv_url)
    if not xml_data:
        print("❌ 无法获取 arXiv 数据，工作流安全退出。")
        exit(1)
        
    root = ET.fromstring(xml_data)
    raw_papers = []
    current_now = datetime.now()
    cutoff_days = int(config_months * 30.5)
    time_filtered_count = 0

    for entry in root.findall('{http://www.w3.org/2005/Atom}entry'):
        title = entry.find('{http://www.w3.org/2005/Atom}title').text.strip().replace('\n', ' ')
        summary = entry.find('{http://www.w3.org/2005/Atom}summary').text.strip().replace('\n', ' ')
        paper_url = entry.find('{http://www.w3.org/2005/Atom}id').text
        published_raw = entry.find('{http://www.w3.org/2005/Atom}published').text
        
        try:
            dt = datetime.strptime(published_raw, "%Y-%m-%dT%H:%M:%SZ")
            published_date = dt.strftime("%Y-%m-%d")
            days_diff = (current_now - dt).days
            if days_diff > cutoff_days:
                time_filtered_count += 1
                continue 
        except:
            published_date = published_raw[:10]
            
        raw_papers.append({'title': title, 'summary': summary, 'url': paper_url, 'date': published_date})

    print(f"📊 arXiv 初筛完成：成功捕获近 {config_months} 个月内论文 {len(raw_papers)} 篇。")

    database_file = "paper_database.json"
    historical_data = []
    if os.path.exists(database_file):
        try:
            with open(database_file, "r", encoding="utf-8") as f:
                historical_data = json.load(f)
        except:
            historical_data = []

    valid_existing_urls = {
        p['url'] for p in historical_data 
        if '失败' not in p.get('review', '') and 'error' not in p.get('review', '').lower() and '503' not in p.get('review', '')
    }
    
    historical_data = [
        p for p in historical_data 
        if (current_now - datetime.strptime(p['date'], "%Y-%m-%d")).days <= cutoff_days
    ]

    api_key = os.getenv("LLM_API_KEY")
    filtered_new_papers = [] 

    if raw_papers and api_key:
        TOP_VENUES = ["isca", "micro", "hpca", "asplos", "ieee tc", "taco", "cal", "sigmetrics"]
        
        for paper in raw_papers:
            if paper['url'] in valid_existing_urls:
                continue
                
            historical_data = [p for p in historical_data if p['url'] != paper['url']]
            print(f"🧠 官方原生 Gemini 智能审查文献: {paper['title'][:60]}...")
            
            # 限制请求速率，防止触发官方基础限流（每篇论文间休息 2 秒）
            time.sleep(2)

            # 第一阶段 - AI 智能语义精筛
            judge_prompt = (
                f"你是一个精通计算机体系结构（Computer Architecture）的审稿人。\n"
                f"请帮我判断下面这篇论文是否属于【处理器微架构、硬件预取器（Hardware Prefetcher）设计、缓存子系统（Cache Subsystem）优化、或存储墙缓解技术】的科学研究？\n"
                f"注意：如果是纯网页前端预取（Web/HTML prefetch）、5G/蜂窝网络数据预取（Network cdn prefetch），请判定为【否】。\n"
                f"请严格只回答【是】或【否】，不要包含任何其他多余的字。\n\n"
                f"标题: {paper['title']}\n"
                f"摘要: {paper['summary']}"
            )
            
            is_hardware_prefetch = ask_gemini_native(judge_prompt, api_key)
            print(f"   裁决结果: [{is_hardware_prefetch}]")
            
            if not is_hardware_prefetch or "是" not in is_hardware_prefetch:
                continue
                
            # 第二阶段 - Semantic Scholar 顶会实时溯源
            venue_info = "📦 arXiv 预印本"
            is_top = False
            try:
                arxiv_id = paper['url'].split('/abs/')[-1].split('v')[0]
                s2_url = f"https://api.semanticscholar.org/graph/v1/paper/arXiv:{arxiv_id}?fields=venue,publicationVenue"
                s2_bytes = robust_http_request(s2_url)
                if s2_bytes:
                    s2_data = json.loads(s2_bytes.decode('utf-8'))
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
            except:
                pass

            # 第三阶段 - 官方原生真实同行评审意见输出
            review_prompt = (
                f"你是一个精通计算机体系结构、微架构和存储子系统的顶级科学家。\n"
                f"请认真阅读以下硬件预取相关论文的标题和摘要，为其撰写一条真实、客观、严谨且高屋建瓴的【专家解读】。\n"
                f"要求用中文，分为两部分回答（总字数控制在150字以内）：\n"
                f"1. 核心创新：阐明其相较于传统预取器在微架构设计或算法上的核心突破点。\n"
                f"2. 潜在价值：分析该方法对缓解存储墙或提升特定负载（如图计算、大模型推理）的实际工业价值。\n\n"
                f"标题: {paper['title']}\n"
                f"摘要: {paper['summary']}"
            )
            
            gemini_review = ask_gemini_native(review_prompt, api_key)
            if gemini_review:
                gemini_review = gemini_review.replace('\n', '<br>')
            else:
                gemini_review = "专家解读临时生成失败。"
            
            paper['venue'] = venue_info
            paper['is_top'] = is_top
            paper['review'] = gemini_review
            
            historical_data.insert(0, paper)
            filtered_new_papers.append(paper)

    historical_data = historical_data[:35]

    with open(database_file, "w", encoding="utf-8") as f:
        json.dump(historical_data, f, ensure_ascii=False, indent=2)

    # 4. 渲染静态主页
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
                <span>📅 发表时间: <strong>{p['date']}</strong></span>
                <span>🔗 <a href="{p['url']}" target="_blank">查看 arXiv 官方原文</a></span>
            </div>
            <div class="card-analysis">
                <h3>🔬 AI 真实学术解读：</h3>
                <p>{p.get('review', '暂无解读')}</p>
            </div>
        </div>
        """

    if not html_cards:
        html_cards = f"<p style='text-align:center; color:#64748b;'>科研雷达正在搜索中，近 {config_months} 个月内暂无最新硬件预取文献。</p>"

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
            <h1>🚀 处理器预取算法文献追踪大屏</h1>
            <p>已锁定期限：仅呈现近 {config_months} 个月内发表的硬核前沿技术</p>
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
        
    # ==========================================
    # 【主动推送模块】
    # ==========================================
    webhook_url = os.getenv("WEBHOOK_URL")
    if filtered_new_papers and webhook_url:
        print("📢 正在向手机端推送今日新增文献...")
        push_text = f"🔥 【处理器预取雷达】今日新增 {len(filtered_new_papers)} 篇核心架构论文！\n\n"
        for idx, p in enumerate(filtered_new_papers):
            clean_review = p['review'].replace("<br>", "\n")
            push_text += f"📌 [{idx+1}] {p['title']}\n"
            push_text += f"📅 时间: {p['date']} | {p['venue']}\n"
            push_text += f"💡 AI专家解读:\n{clean_review}\n"
            push_text += f"🔗 原文: {p['url']}\n"
            push_text += "------------------------\n"
        
        payload = {"msg_type": "text", "content": {"text": push_text}}
        headers = {"Content-Type": "application/json"}
        req = urllib.request.Request(webhook_url, data=json.dumps(payload).encode('utf-8'), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                print("✅ 手机端消息弹窗成功送达！")
        except Exception as e:
            print(f"❌ 主动推送失败: {e}")

    print("🎯 【官方直连高保版】网页与调度引擎同步刷新成功！")

if __name__ == "__main__":
    main()
