"""Shared relevance checks. Source names and query labels are not article evidence."""
from __future__ import annotations

import re

RESEARCH = re.compile(r"财报|营收|净利润|盈利预测|估值|上市公司|产业链|行业研究|行业报告|投资逻辑|业绩|并购|重组|回购|分红|融资|招股|IPO|票房.{0,12}(增长|同比|收入)|市场规模", re.I)
GOSSIP = re.compile(r"生日|庆生|生快|恋情|绯闻|官宣恋爱|出轨|分手|复合|塌房|嗑CP|磕CP|粉丝应援|机场穿搭|红毯造型|路透照|生图|颜值|追星|饭圈|吃瓜|八卦", re.I)
PROMOTION = re.compile(r"扫码.{0,10}(领取|进群|购买)|加微信|购买链接|限时.{0,8}(优惠|秒杀)|抽奖|免费送|招商加盟|课程报名|训练营")
LIFESTYLE = re.compile(r"明星|综艺|电视剧|穿搭|美妆|护肤|减肥|瘦身|育儿|星座|情感|宠物|探店|菜谱|婚礼|婚恋|娱乐|演唱会")


def article_text(item: dict) -> str:
    return ' '.join(str(item.get(k) or '') for k in ('title', 'summary', 'description', 'desc', 'content'))[:30000]


def noise_reason(item: dict) -> str | None:
    title = str(item.get('title') or '')
    text = article_text(item)
    # Explicit research in the title can discuss entertainment-sector companies.
    research_title = bool(RESEARCH.search(title))
    if GOSSIP.search(title) and not research_title:
        return 'entertainment_gossip'
    if PROMOTION.search(title) and not research_title:
        return 'promotion'
    if research_title:
        return None
    if GOSSIP.search(text) and not RESEARCH.search(text):
        return 'entertainment_gossip'
    if LIFESTYLE.search(text) and not RESEARCH.search(text):
        return 'lifestyle'
    return None
