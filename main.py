import os
import re
import sys
import time
import json
import yaml
import urllib.request
import urllib.parse
from datetime import datetime
import xml.etree.ElementTree as ET

# ==========================================
# 核心配置兜底（若config.yaml读取失败时激活）
# ==========================================
DEFAULT_CONFIG = {
    "search_queries": ["ti:prefetch OR ti:prefetcher OR key:prefetch OR key:prefetcher"],
    "time_window": {"months": 6},
    "filter_rules": {
        "include": ["prefetch", "prefetcher"],
        "exclude": ["fpga", "dram", "pcm", "reram", "cryptography", "security"]
    }
}

def load_config():
    """安全加载配置文件"""
    if os.path.exists("config.yaml"):
        try:
            with open("config.yaml", "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"⚠️ 读取 config.yaml 失败，使用 system 内置兜底配置. 原因: {e}")
    return DEFAULT_CONFIG

def robust_http_request(url, data=None, headers=None, method="GET", retries=3, timeout=15):
    """工业级稳健网络请求函数（带指数退避重试）"""
    if headers is None:
        headers = {
            "User-Agent": "Academic-Prefetch-Agent/2.0 (Automated Architecture Paper Radar)"
        }
    
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                if response.status == 200:
                    return response.read()
                elif response.status == 429:
                    sleep_time = (attempt + 1) * 8
                    print(f"⚠️ 遭遇 429 限流炸弹！触发自愈，休眠 {sleep_time} 秒后重试...")
                    time.sleep(sleep_time)
                elif response.status in [500, 502, 503, 504]:
                    sleep_time = (attempt + 1) * 5
                    print(f"⚠️ 服务器错误 {response.status}，休眠 {sleep_time} 秒后重试...")
                    time.sleep(sleep_time)
        except Exception as e:
            sleep_time = (attempt + 1) * 5
            print(f"⚠️ 网络请求异常: {e}，将在 {sleep_time} 秒后进行第 {attempt + 1} 次重试...")
            time.sleep(sleep_time)
            
    return None

def ask_gemini_native_safe(prompt, api_key, model="gemini-2.5-flash"):
    """使用原生 urllib 安全请求 Google Gemini 官方接口，自带防 429 熔断"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "temperature": 0.1,  # 降低随机性，卡死红线标准
            "maxOutputTokens": 300
        }
    }
    
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    
    response_bytes = robust_http_request(url, data=data, headers=headers, method="POST", retries=4)
    if not response_bytes:
        return None
        
    try:
        result = json.loads(response_bytes.decode("utf-8"))
        return result['candidates'][0]['content']['parts'][0]['text'].strip()
    except Exception as e:
        print(f"⚠️ 解析 Gemini 返回数据失败: {e}")
        return None

def fetch_arxiv_papers(queries, max_results=40):
    """从 arXiv 海选拉取最新候选论文（只认标题与关键词组合）"""
    combined_query = " AND ".join([f"({q})" for q in queries])
    encoded_query = urllib.parse.quote(combined_query)
    url = f"http://export.arxiv.org/api/query?search_query={encoded_query}&max_results={max_results}&sortBy=lastUpdatedDate&sortOrder=descending"
    
    print(f"🌐 正在向 arXiv 服务器发起海选请求...")
    xml_data = robust_http_request(url)
    if not xml_data:
        print("❌ 无法连接到 arXiv API，本次海选终止。")
        return []
        
    try:
        root = ET.fromstring(xml_data)
        namespace = {'atom': 'http://www.w3.org/2005/Atom'}
        papers = []
        
        for entry in root.findall('atom:entry', namespace):
            title = entry.find('atom:title', namespace).text
            title = re.sub(r'\s+', ' ', title).strip()
            
            summary = entry.find('atom:summary', namespace).text
            summary = re.sub(r'\s+', ' ', summary).strip()
            
            url_str = entry.find('atom:id', namespace).text.strip()
            published_str = entry.find('atom:published', namespace).text.strip()
            
            date_obj = datetime.strptime(published_str[:10], "%Y-%m-%d")
            formatted_date = date_obj.strftime("%Y-%m-%d")
            
            papers.append({
                "title": title,
                "summary": summary,
                "url": url_str,
                "date": formatted_date
            })
        print(f"📥 arXiv 海选完毕，成功抓取到最新的 {len(papers)} 篇候选文献。")
        return papers
    except Exception as e:
        print(f"❌ 解析 arXiv XML 失败: {e}")
        return []

def send_webhook_notification(papers):
    """如果配置了系统 webhook，自动发送动态推送"""
    webhook_url = os.getenv("SYS_WEBHOOK_URL")
    if not webhook_url or not papers:
        return
        
    print(f"🔔 正在向手机端推送最新捕获的 {len(papers)} 篇硬核论文...")
    for paper in papers:
        clean_review = paper['review'].replace('<br>', '\n')
        
        card_text = (
            f"👑 发现微架构硬件预取前沿论文！\n\n"
            f"📄 标题: {paper['title']}\n"
            f"📅 时间: {paper['date']}\n"
            f"🏅 认证: {paper['venue']}\n\n"
            f"🧠 专家解读:\n{clean_review}\n\n"
            f"🔗 链接: {paper['url']}"
        )
        
        payload = {
            "msg_type": "text",
            "content": {"text": card_text}
        }
        
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        robust_http_request(webhook_url, data=data, headers=headers, method="POST")
        time.sleep(2)

def render_html_page(papers):
    """无冲突生成 GitHub Pages 大屏幕"""
    html_template = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>硬件预取器 (Hardware Prefetcher) 前沿学术雷达</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background-color: #f4f6f9; color: #333; margin: 0; padding: 20px; }
        .container { max-width: 1000px; margin: 0 auto; }
        header { text-align: center; margin-bottom: 30px; border-bottom: 2px solid #e1e4e8; padding-bottom: 20px; }
        h1 { color: #1a202c; margin-bottom: 5px; }
        .subtitle { color: #718096; font-size: 0.95rem; }
        .card { background: white; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); padding: 20px; margin-bottom: 20px; border-left: 5px solid #4a5568; transition: transform 0.2s; }
        .card:hover { transform: translateY(-2px); }
        .card.top-tier { border-left-color: #d69e2e; background-color: #fffdf5; }
        .meta-row { display: flex; justify-content: space-between; font-size: 0.85rem; color: #718096; margin-bottom: 12px; font-weight: 500; }
        .venue { padding: 2px 8px; border-radius: 4px; background: #e2e8f0; color: #4a5568; }
        .card.top-tier .venue { background: #feebc8; color: #c05621; }
        .title { font-size: 1.25rem; font-weight: 700; color: #2d3748; margin-bottom: 12px; text-decoration: none; display: inline-block; }
        .title:hover { color: #3182ce; }
        .review-box { background: #f7fafc; border-radius: 6px; padding: 15px; border: 1px dashed #e2e8f0; font-size: 0.92rem; line-height: 1.6; color: #2d3748; }
        .card.top-tier .review-box { background: #fffaf0; border-color: #fbd38d; }
        .tag { font-weight: bold; color: #4a5568; display: block; margin-bottom: 4px; text-transform: uppercase; font-size: 0.8rem; letter-spacing: 0.5px; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>📡 硬件预取器前沿学术雷达</h1>
            <div class="subtitle">只关注微架构预取设计与算法优化 | 物理级标题硬过滤机制 | 自动更新时间：UPDATE_TIME</div>
        </header>
        <main>
            <!-- CARDS_PLACEHOLDER -->
        </main>
    </div>
</body>
</html>
"""
    cards_html = []
    for p in papers:
        is_top_class = "top-tier" if p.get('is_top', False) else ""
        card = f"""
        <div class="card {is_top_class}">
            <div class="meta-row">
                <span>📅 发表日期: {p['date']}</span>
                <span class="venue">{p['venue']}</span>
            </div>
            <a class="title" href="{p['url']}" target="_blank">{p['title']}</a>
            <div class="review-box">
                <span class="tag">💡 专家学术解读：</span>
                {p['review']}
            </div>
        </div>
        """
        cards_html.append(card)
        
    if not cards_html:
        cards_html.append("<p style='text-align:center; color:#718096; margin-top:50px;'>近期暂无符合微架构硬件预取标准的最新顶会论文。</p>")
        
    final_html = html_template.replace("<!-- CARDS_PLACEHOLDER -->", "\n".join(cards_html))
    final_html = final_html.replace("UPDATE_TIME", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(final_html)
    print("🖥️ 动态大屏 index.html 渲染成功。")

def main():
    print("🚀 === 硬件预取器学术特工系统 2.0 启动 ===")
    config = load_config()
    
    months_window = config.get("time_window", {}).get("months", 6)
    current_now = datetime.now()
    cutoff_days = months_window * 30
    
    historical_data = []
    if os.path.exists("paper_database.json"):
        try:
            with open("paper_database.json", "r", encoding="utf-8") as f:
                historical_data = json.load(f)
        except:
            historical_data = []
            
    historical_data = [
        p for p in historical_data 
        if (current_now - datetime.strptime(p['date'], "%Y-%m-%d")).days <= cutoff_days
    ]
    
    valid_existing_urls = {p['url'] for p in historical_data if "专家解读生成失败" not in p.get('review', '')}
    
    raw_papers = fetch_arxiv_papers(config["search_queries"], max_results=40)
    
    api_key = os.getenv("LLM_API_KEY")
    filtered_new_papers = []
    
    if raw_papers and api_key:
        TOP_VENUES = ["isca", "micro", "hpca", "asplos", "ieee tc", "taco", "cal", "sigmetrics"]
        
        for paper in raw_papers:
            if paper['url'] in valid_existing_urls:
                continue
                
            historical_data = [p for p in historical_data if p['url'] != paper['url']]
            
            title_lower = paper['title'].lower()
            summary_lower = paper['summary'].lower()
            
            # =======================================================
            # 🛡️【硬过滤核心重组：Include 优先拦截 -> Exclude 绝对熔断】
            # =======================================================
            
            # 1. 优先判断 Include 内容：标题不含任何核心白名单词，直接出局
            if not any(inc in title_lower for inc in config["filter_rules"]["include"]):
                print(f"⏩ [物理硬拦截] 标题未直接包含 prefetch，安全跳过: {paper['title'][:50]}...")
                continue
                
            # 2. 继而判断 Exclude 内容：一旦标题或摘要包含黑名单词，立刻一刀切熔断
            if any(exc in title_lower or exc in summary_lower for exc in config["filter_rules"]["exclude"]):
                print(f"⏩ [黑名单拦截] 确定含有黑名单干扰内容，物理过滤: {paper['title'][:50]}...")
                continue
                
            if (current_now - datetime.strptime(paper['date'], "%Y-%m-%d")).days > cutoff_days:
                continue

            print(f"🧠 钢铁审查文献: {paper['title'][:60]}...")
            time.sleep(8)

            # 第一阶段 - AI 智能语义精筛（聚焦处理器核心与微架构层级）
            judge_prompt = (
                f"你是一个体系结构微架构方向的冷酷审稿人。\n"
                f"请严格帮我判断：这篇论文的核心贡献是否属于【处理器硬件预取器（Hardware Prefetcher）架构设计、预取算法优化、或取指单元（Fetch Unit）改进】？\n"
                f"只有当论文确实在设计、改进或评测硬件预取器本身时，才回答【是】。其他擦边、应用层、或纯存储器介质的研究一律回答【否】。\n"
                f"请严格只回答【是】或【否】，不要包含任何其他多余的字。\n\n"
                f"标题: {paper['title']}\n"
                f"摘要: {paper['summary']}"
            )
            
            is_hardware_prefetch = ask_gemini_native_safe(judge_prompt, api_key)
            print(f"   裁决结果: [{is_hardware_prefetch}]")
            
            if not is_hardware_prefetch or "是" not in is_hardware_prefetch:
                continue
                
            # 第二阶段 - Semantic Scholar 顶会实时逆向溯源
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

            time.sleep(4)

            # 第三阶段 - 顶尖科学家同行评审意见输出
            review_prompt = (
                f"你是一个精通计算机体系结构、微架构和存储子系统的顶级科学家。\n"
                f"请认真阅读以下硬件预取相关论文的标题和摘要，为其撰写一条真实、客观、严谨且高屋建瓴的【专家解读】。\n"
                f"要求用中文，分为两部分回答（总字数控制在150字以内）：\n"
                f"1. 核心创新：阐明其相较于传统预取器在微架构设计或算法上的核心突破点。\n"
                f"2. 潜在价值：分析该方法对缓解存储墙或提升特定负载（如图计算、大模型推理）的实际工业价值。\n\n"
                f"标题: {paper['title']}\n"
                f"摘要: {paper['summary']}"
            )
            
            gemini_review = ask_gemini_native_safe(review_prompt, api_key)
            if gemini_review:
                gemini_review = gemini_review.replace('\n', '<br>')
            else:
                gemini_review = "专家解读生成失败（触发频控限制）。"
            
            paper['venue'] = venue_info
            paper['is_top'] = is_top
            paper['review'] = gemini_review
            
            historical_data.insert(0, paper)
            filtered_new_papers.append(paper)

    historical_data.sort(key=lambda x: x['date'], reverse=True)
    historical_data = historical_data[:35]
    
    with open("paper_database.json", "w", encoding="utf-8") as f:
        json.dump(historical_data, f, ensure_ascii=False, indent=2)
        
    render_html_page(historical_data)
    send_webhook_notification(filtered_new_papers)
    print("🏁 === 本轮自动追踪学术雷达已安全闭环 ===")

if __name__ == "__main__":
    main()
