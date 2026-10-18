"""Additional public feeds and Agent Reach's installed read-only backends."""
from __future__ import annotations

import json
import hashlib
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
from xml.etree import ElementTree

import requests
import yaml
from pydantic import BaseModel, Field
from typing import Literal

from .link_preview import _validate_public_http_url
from .media_collector_store import _collector_data_dir


class SocialSource(BaseModel):
    platform: Literal['rss', 'v2ex', 'twitter', 'reddit', 'bilibili', 'xiaohongshu', 'facebook', 'instagram']
    query: str = Field(default='', max_length=300)
    enabled: bool = True


class SocialSourcesConfig(BaseModel):
    sources: list[SocialSource] = Field(default_factory=lambda: [SocialSource(platform='v2ex'),
        SocialSource(platform='rss', query='https://hnrss.org/frontpage')], max_length=20)


def _executable(name: str) -> str | None:
    path = shutil.which(name)
    fallback = Path.home()/'.local/bin'/name
    return path or (str(fallback) if fallback.is_file() else None)


def reach_status() -> dict:
    binary = _executable('agent-reach')
    if not binary:
        return {'installed': False, 'channels': {}, 'message': '未安装 Agent Reach；RSS 与 V2EX 仍可使用'}
    try:
        p = subprocess.run([binary, 'doctor', '--json'], capture_output=True, text=True, timeout=30)
        channels = json.loads(p.stdout)
        return {'installed': True, 'channels': {k: {'name': v.get('name',k), 'status':v.get('status'),
            'backend':v.get('active_backend')} for k,v in channels.items() if isinstance(v,dict)}}
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return {'installed': True, 'channels': {}, 'message': '渠道检测失败，请检查 Agent Reach 的运行环境'}


def load_sources() -> SocialSourcesConfig:
    path = _collector_data_dir()/'social_sources.json'
    return SocialSourcesConfig.model_validate_json(path.read_text()) if path.exists() else SocialSourcesConfig()


def save_sources(config: SocialSourcesConfig) -> None:
    path = _collector_data_dir()/'social_sources.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(config.model_dump_json(indent=2), encoding='utf-8')


def _get_public(url: str) -> bytes:
    # Validate every redirect before following it. No cookies or private credentials.
    for _ in range(4):
        url = _validate_public_http_url(url)
        with requests.get(url, headers={'User-Agent':'Deepsee/1.0 Agent-Reach-compatible'},
                          timeout=(5,15), allow_redirects=False, stream=True) as response:
            if response.is_redirect:
                url = urljoin(url, response.headers.get('Location',''))
                continue
            response.raise_for_status()
            content = bytearray()
            for chunk in response.iter_content(65536):
                content.extend(chunk)
                if len(content)>2*1024*1024:
                    raise ValueError('订阅源超过 2MB 限制')
            return bytes(content)
    raise ValueError('订阅源重定向过多')


def _rss_items(data: bytes) -> list[dict]:
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('不支持包含实体定义的订阅源')
    root=ElementTree.fromstring(data)
    rows=root.findall('.//item') or root.findall('{http://www.w3.org/2005/Atom}entry')
    items=[]
    for row in rows[:30]:
        def value(key):
            node=row.find(key)
            if node is None: node=row.find('{http://www.w3.org/2005/Atom}'+key)
            return ''.join(node.itertext()).strip() if node is not None else ''
        link=value('link')
        if not link:
            node=row.find('{http://www.w3.org/2005/Atom}link')
            link=node.get('href','') if node is not None else ''
        items.append({'title':value('title'),'url':link,'description':(value('description') or value('summary'))[:1000]})
    return items


def fetch_source(source: SocialSource, health: dict | None = None) -> list[dict]:
    if source.platform=='rss':
        return _rss_items(_get_public(source.query))
    if source.platform=='v2ex':
        rows=json.loads(_get_public('https://www.v2ex.com/api/topics/hot.json'))
        return [{'title':r.get('title',''),'url':r.get('url',''),'description':str(r.get('content',''))[:1000],
                 'extra':{'author':(r.get('member') or {}).get('username','')}} for r in rows[:30]]
    state=(health or reach_status()).get('channels',{}).get(source.platform,{})
    if state.get('backend')!='OpenCLI' or state.get('status')!='ok':
        raise ValueError('该渠道未就绪；请先安装后端并在浏览器中登录，再重新检测')
    binary=_executable('opencli')
    if not binary: raise ValueError('未找到 OpenCLI')
    query=source.query.strip()
    if not query or query.startswith('-'): raise ValueError('请填写搜索词；Instagram 请填写作者用户名')
    action='user' if source.platform=='instagram' else 'search'
    p=subprocess.run([binary,source.platform,action,query,'-f','yaml'],capture_output=True,text=True,timeout=40)
    if p.returncode: raise ValueError('采集失败；请检查浏览器登录、扩展连接或平台限流')
    data=yaml.safe_load(p.stdout)
    if isinstance(data,dict): data=data.get('items') or data.get('data') or data.get('results') or []
    if not isinstance(data,list): raise ValueError('采集后端返回格式不支持')
    items=[]
    for row in data[:30]:
        if not isinstance(row,dict): continue
        items.append({'title':str(row.get('title') or row.get('text') or row.get('content') or '')[:300],
                      'url':str(row.get('url') or row.get('link') or row.get('permalink') or ''),
                      'description':str(row.get('description') or row.get('content') or row.get('text') or '')[:1000],
                      'extra':{'author':str(row.get('author') or row.get('username') or '')}})
    return items


def collect_sources() -> dict:
    sources=[s for s in load_sources().sources if s.enabled]
    health=reach_status() if any(s.platform not in ('rss','v2ex') for s in sources) else {}
    now=datetime.now(timezone.utc).isoformat()
    folder=_collector_data_dir()/'search'/datetime.now().strftime('%Y-%m-%d')/'agent-reach'
    folder.mkdir(parents=True,exist_ok=True)
    results=[]
    active_files = set()
    for source in sources:
        source_id = hashlib.sha256((source.platform + ':' + source.query).encode()).hexdigest()[:12]
        target=folder/f'{source.platform}-{source_id}.json'
        active_files.add(target.name)
        try:
            items=fetch_source(source,health)
            for rank,item in enumerate(items,1): item['rank']=rank
            target.write_text(json.dumps({'fetched_at':now,'platform':source.platform,
                'keyword':source.query,'items':items},ensure_ascii=False),encoding='utf-8')
            results.append({'platform':source.platform,'ok':True,'count':len(items)})
        except (ValueError,OSError,requests.RequestException,subprocess.TimeoutExpired,ElementTree.ParseError) as exc:
            # Do not replace the last successful batch with an empty error result.
            reason=str(exc) if isinstance(exc,ValueError) else '采集失败或超时；保留上次成功数据'
            results.append({'platform':source.platform,'ok':False,'error':reason[:180]})
    for old in folder.glob('*.json'):
        if old.name not in active_files:
            old.unlink()
    return {'ok':all(r['ok'] for r in results),'results':results,'count':sum(r.get('count',0) for r in results)}
