import os
import urllib.request
import urllib.parse  # 导入用于处理 URL 编码的库
import xml.etree.ElementTree as ET
import yaml
from google import genai

# 1. 加载本地过滤配置文件
with open('config.yaml', 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

# 2. 从 arXiv 检索最新的预取论文
print("🚀 正在从 arXiv 实时抓取最新的预取领域文献...")

# 【修复核心】：使用 urllib.parse.quote 对含双引号和逻辑词的 query 进行安全编码
raw_query = config['search_queries'][0]
encoded_query = urllib.parse.quote(raw_query)

# 拼接成标准的 API 请求链接
url = f'http://export.arxiv.org/api/query?search_query={encoded_query}&max_results=20&sortBy=submittedDate&sortOrder=descending'
print(f"🔗 正在请求的 API 链接: {url}")

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
    papers.append({'title': title, 'summary': summary, 'url': paper_url})

# 3. 硬件预取规则硬核过滤
filtered_papers = []
for p in papers:
    text_to_check = (p['title'] + " " + p['summary']).lower()
    has_include = any(word in text_to_check for word in config['filter_rules']['include'])
    has_exclude = any(word in text_to_check for word in config['filter_rules']['exclude'])
    if has_include and not has_exclude:
        filtered_papers.append(p)

print(f"💡 本次检索共捕获到 {len(papers)} 篇包含预取字眼的原始论文。")
print(f"🎯 经过硬件子系统、缓存预取规则严格清洗后，剩余 {len(filtered_papers)} 篇核心架构论文。\n")

# 4. 接入官方免费的 Gemini 进行硬核结构化总结
api_key = os.getenv("LLM_API_KEY")
if filtered_papers and api_key:
    # 初始化 Google Gemini 官方客户端
    client = genai.Client(api_key=api_key)
    
    for idx, paper in enumerate(filtered_papers):
        prompt = (
            f"你是一个精通计算机体系结构（Computer Architecture）的专家。\n"
            f"请用两句话将下面这篇硬件预取算法论文的【核心创新点】和【实验效果】翻译并提炼为通俗易懂的中文：\n\n"
            f"标题: {paper['title']}\n"
            f"摘要: {paper['summary']}"
        )
        try:
            # 调用官方推荐的免费且速度极快的 gemini-2.5-flash 模型
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
            )
            print(f"📌 [论文 {idx+1}]")
            print(f"【👉 标题】: {paper['title']}")
            print(f"【🔗 链接】: {paper['url']}")
            print(f"【💡 Gemini专家解读】:\n{response.text}\n")
            print("-" * 50)
        except Exception as e:
            print(f"调用 Gemini 失败: {e}")
else:
    print("今日没有发现符合硬件预取标准的最新论文，或者未在 GitHub 配置 LLM_API_KEY。")
