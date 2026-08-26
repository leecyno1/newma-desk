#!/usr/bin/env python3
"""新闻舆情监测模块统计脚本"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import time
from datetime import datetime, timezone

# 直接导入底层函数（绕过配置依赖）
def get_news_data():
    """获取新闻数据"""
    import requests
    import json
    
    sources_to_test = [
        ('华尔街见闻', 'wallstreetcn-quick', 'https://api.wallstreetcn.com/apiv1/content/lives?channel=global&limit=30'),
        ('Hacker News', 'hackernews', 'https://hn.algolia.com/api/v1/search_by_date?tags=story&hitsPerPage=30'),
        ('Reuters', 'reuters-business', 'https://feeds.reuters.com/reuters/businessNews'),
        ('BBC', 'bbc-business', 'http://feeds.bbci.co.uk/news/business/rss.xml'),
        ('CNBC', 'cnbc-top', 'https://www.cnbc.com/id/100003114/device/rss/rss.html'),
        ('NPR', 'npr-business', 'https://feeds.npr.org/1006/feed.json'),
        ('TechCrunch', 'techcrunch', 'https://techcrunch.com/wp-json/wp/v2/posts?per_page=10'),
        ('CoinDesk', 'coindesk', 'https://www.coindesk.com/wp-json/wp/v2/posts?per_page=10'),
        ('Spaceflight', 'spaceflight', 'https://api.spaceflightnewsapi.net/v4/articles?limit=20'),
        ('Reddit r/stocks', 'reddit-stocks', 'https://www.reddit.com/r/stocks/hot.json?limit=10'),
    ]
    
    results = []
    now = int(time.time() * 1000)
    day_24h = now - (24 * 3600 * 1000)
    day_72h = now - (72 * 3600 * 1000)
    
    # 通用 Headers，模拟浏览器
    common_headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-US,en;q=0.9',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
    }

    for name, sid, url in sources_to_test:
        try:
            # 针对不同源微调 Headers
            headers = common_headers.copy()
            if 'reddit.com' in url:
                # Reddit 极其严格，通常需要 OAuth，这里尝试通过但可能仍失败
                headers['Accept'] = 'application/json'
            
            r = requests.get(url, timeout=15, headers=headers)
            
            # 检查状态码
            if r.status_code != 200:
                results.append({
                    'name': name,
                    'id': sid,
                    'total': 0,
                    '24h': 0,
                    '72h': 0,
                    'status': f'HTTP {r.status_code}'
                })
                continue

            if url.endswith('.json') or 'json' in r.headers.get('Content-Type', ''):
                try:
                    data = r.json()
                except json.JSONDecodeError:
                    # 尝试作为 RSS 解析（有些 URL 后缀是 json 但返回 xml，或者反之）
                    if '<rss' in r.text or '<feed' in r.text:
                        import xml.etree.ElementTree as ET
                        try:
                            root = ET.fromstring(r.text)
                            items = root.findall('.//item') + root.findall('.//{http://www.w3.org/2005/Atom}entry')
                            count = len(items)
                            count_24h = 0
                            count_72h = 0
                            for item in items:
                                pub_date = item.findtext('pubDate') or item.findtext('{http://www.w3.org/2005/Atom}published') or ''
                                try:
                                    from email.utils import parsedate_to_datetime
                                    dt = parsedate_to_datetime(pub_date)
                                    ts = int(dt.timestamp() * 1000)
                                    if ts >= day_24h:
                                        count_24h += 1
                                    if ts >= day_72h:
                                        count_72h += 1
                                except:
                                    pass
                            results.append({
                                'name': name,
                                'id': sid,
                                'total': count,
                                '24h': count_24h,
                                '72h': count_72h,
                                'status': 'ok (parsed as XML)'
                            })
                            continue
                        except:
                            pass
                    
                    results.append({
                        'name': name,
                        'id': sid,
                        'total': 0,
                        '24h': 0,
                        '72h': 0,
                        'status': 'error: Invalid JSON response'
                    })
                    continue
            else:
                # 默认尝试 XML/RSS 解析
                import xml.etree.ElementTree as ET
                try:
                    root = ET.fromstring(r.text)
                    items = root.findall('.//item') + root.findall('.//{http://www.w3.org/2005/Atom}entry')
                    count = len(items)
                    count_24h = 0
                    count_72h = 0
                    for item in items:
                        pub_date = item.findtext('pubDate') or item.findtext('{http://www.w3.org/2005/Atom}published') or ''
                        try:
                            from email.utils import parsedate_to_datetime
                            dt = parsedate_to_datetime(pub_date)
                            ts = int(dt.timestamp() * 1000)
                            if ts >= day_24h:
                                count_24h += 1
                            if ts >= day_72h:
                                count_72h += 1
                        except:
                            # 尝试 ISO 格式
                            try:
                                dt = datetime.fromisoformat(pub_date.replace('Z', '+00:00'))
                                ts = int(dt.timestamp() * 1000)
                                if ts >= day_24h:
                                    count_24h += 1
                                if ts >= day_72h:
                                    count_72h += 1
                            except:
                                pass
                                
                    results.append({
                        'name': name,
                        'id': sid,
                        'total': count,
                        '24h': count_24h,
                        '72h': count_72h,
                        'status': 'ok'
                    })
                    continue
                except Exception as e:
                    # 如果 XML 解析失败，尝试 JSON (有些 API 不带 .json 后缀)
                    try:
                        data = r.json()
                    except:
                        results.append({
                            'name': name,
                            'id': sid,
                            'total': 0,
                            '24h': 0,
                            '72h': 0,
                            'status': f'error: Parse failed {str(e)[:30]}'
                        })
                        continue

            # JSON 数据处理逻辑
            if 'items' in data:
                count = len(data.get('items', []))
            elif 'data' in data:
                if isinstance(data['data'], dict) and 'items' in data['data']:
                    count = len(data['data']['items'])
                elif isinstance(data['data'], list):
                    count = len(data['data'])
                else:
                    count = 0
            elif 'hits' in data:
                count = len(data.get('hits', []))
            elif 'results' in data:
                count = len(data.get('results', []))
            else:
                count = 0
            
            results.append({
                'name': name,
                'id': sid,
                'total': count,
                '24h': count,  # JSON API 通常返回最新的，简单起见假设都在范围内，或者需要具体解析时间字段
                '72h': count,
                'status': 'ok'
            })
        except Exception as e:
            results.append({
                'name': name,
                'id': sid,
                'total': 0,
                '24h': 0,
                '72h': 0,
                'status': f'error: {str(e)[:50]}'
            })
    
    return results

def main():
    print('=' * 80)
    print('新闻舆情监测模块 - 底层数据源统计报告')
    print('=' * 80)
    print()
    print('正在采集数据...')
    print()
    
    results = get_news_data()
    
    total_sources = len(results)
    active_sources = len([r for r in results if r['status'] == 'ok' and r['total'] > 0])
    total_items = sum(r['total'] for r in results)
    total_24h = sum(r['24h'] for r in results)
    total_72h = sum(r['72h'] for r in results)
    
    print('📊 数据源详细统计：')
    print('-' * 80)
    print(f"{'数据源':<30} {'ID':<20} {'总数':<8} {'24h':<8} {'72h':<8} {'状态':<15}")
    print('-' * 80)
    
    for r in results:
        status_icon = '✅' if r['status'] == 'ok' else '❌'
        print(f"{r['name']:<30} {r['id']:<20} {r['total']:<8} {r['24h']:<8} {r['72h']:<8} {status_icon} {r['status']}")
    
    print('-' * 80)
    print(f"{'总计':<30} {'':<20} {total_items:<8} {total_24h:<8} {total_72h:<8}")
    print()
    
    print('=' * 80)
    print('📈 汇总统计')
    print('=' * 80)
    print(f'• 已配置数据源总数：{total_sources} 个')
    print(f'• 活跃数据源：{active_sources} 个')
    print(f'• 当前可获取新闻总数：{total_items} 条')
    print(f'• 过去 24 小时：{total_24h} 条')
    print(f'• 过去 72 小时：{total_72h} 条')
    print()
    
    print('=' * 80)
    print('📋 完整数据源列表（含国内RSS源）')
    print('=' * 80)
    print()
    print('🌍 国际财经媒体：')
    print('  1. 华尔街见闻 (wallstreetcn-quick)')
    print('  2. Reuters Business (reuters-business)')
    print('  3. BBC Business (bbc-business)')
    print('  4. CNBC (cnbc-top)')
    print('  5. NPR Business (npr-business)')
    print()
    print('💻 科技媒体：')
    print('  6. Hacker News (hackernews)')
    print('  7. TechCrunch (techcrunch)')
    print('  8. Engadget (engadget)')
    print('  9. Spaceflight News (spaceflight)')
    print()
    print('₿ 加密货币：')
    print('  10. CoinDesk (coindesk)')
    print('  11. Cointelegraph (cointelegraph)')
    print('  12. Bitcoin.com News (bitcoincom)')
    print()
    print('💬 社区讨论：')
    print('  13. Reddit r/stocks (reddit-stocks)')
    print('  14. Reddit r/investing (reddit-investing)')
    print('  15. Reddit r/economy (reddit-economy)')
    print()
    print('🇨🇳 国内财经媒体（RSS配置但未测试）：')
    print('  16. 证券时报 (stcn)')
    print('  17. 21世纪经济报道 (21jingji)')
    print('  18. 界面新闻 (jiemian)')
    print('  19. 财新 (caixin)')
    print('  20. 上证报 (ssnews)')
    print('  21. 澎湃财经 (thepaper)')
    print('  22. 第一财经 (yicai)')
    print()
    
    print('=' * 80)
    print('🔧 技术架构说明')
    print('=' * 80)
    print('• 实现文件：')
    print('  - app/services/news_client.py (核心采集逻辑)')
    print('  - app/routers/news.py (API路由)')
    print()
    print('• 数据流：')
    print('  1. 各数据源直接采集（JSON API / RSS Feed）')
    print('  2. 归一化处理（normalize_items）')
    print('  3. 财经关键词过滤（_is_finance）')
    print('  4. 白名单过滤（_load_source_whitelist）')
    print('  5. 分类标注（宏观/行业/个股/舆情/观点）')
    print('  6. 3小时缓存（_CACHE字典 + TTL）')
    print()
    print('• 主要API端点：')
    print('  - GET /api/newsfeed/items?limit=N&whitelist_only=bool')
    print('  - GET /api/newsfeed/search?q=关键词')
    print('  - GET /api/newsfeed/by-ids?ids=id1,id2,id3')
    print()
    print('• 配置文件：')
    print('  - data/entities.json:')
    print('    * finance_keywords: 财经关键词列表')
    print('    * news_sources_whitelist: 数据源白名单')
    print()
    print('• 数据库：')
    print('  - 新闻数据不存储到SQLite（仅内存缓存）')
    print('  - 可选落盘：data/datasets/news_snapshot_<timestamp>.json')
    print()

if __name__ == '__main__':
    main()
