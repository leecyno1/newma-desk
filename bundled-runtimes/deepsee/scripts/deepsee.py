#!/usr/bin/env python3
"""Deepsee read-only CLI. Uses the same project API as any other client."""
import argparse
import json
import os
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def parser():
    root = argparse.ArgumentParser(description='Deepsee 数据查询；密钥由 DEEPSEE_API_KEY 环境变量提供。')
    root.add_argument('--base', default=os.getenv('DEEPSEE_API_BASE', 'http://127.0.0.1:8001/api/v1'))
    commands = root.add_subparsers(dest='command', required=True)
    commands.add_parser('capabilities', help='查看可用资源和额度')
    for name in ('messages', 'contacts', 'chats', 'emails', 'articles', 'meetings'):
        cmd = commands.add_parser(name)
        cmd.add_argument('--q')
        cmd.add_argument('--limit', type=int, default=100)
        if name in {'messages', 'contacts', 'chats', 'emails'}:
            cmd.add_argument('--cursor')
        else:
            cmd.add_argument('--offset', type=int, default=0)
        if name in {'messages', 'emails'}:
            cmd.add_argument('--after-id', type=int)
        if name == 'messages':
            for field in ('chat-id', 'sender-id', 'since', 'until'):
                cmd.add_argument(f'--{field}')
        if name == 'articles':
            cmd.add_argument('--source', required=True, choices=['news', 'media', 'mp'])
    search = commands.add_parser('search', help='按来源分组搜索；不是语义搜索')
    search.add_argument('q'); search.add_argument('--sources')
    search.add_argument('--limit', type=int, default=20); search.add_argument('--offset', type=int, default=0)
    score = commands.add_parser('scorecard', help='读取联系人评分证据')
    score.add_argument('contact_id'); score.add_argument('--limit', type=int, default=20)
    score.add_argument('--offset', type=int, default=0)
    media = commands.add_parser('attachment', help='下载已留存的消息附件')
    media.add_argument('message_id', type=int); media.add_argument('--output', type=Path, required=True)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    key = os.getenv('DEEPSEE_API_KEY', '').strip()
    if not key:
        print('请先设置 DEEPSEE_API_KEY；不要把密钥放进命令参数。', file=sys.stderr)
        return 2
    base = args.base.rstrip('/')
    url = urlsplit(base)
    if (url.scheme not in {'http', 'https'} or not url.hostname or url.username or url.password
            or url.query or url.fragment
            or (url.scheme == 'http' and url.hostname not in {'127.0.0.1', 'localhost', '::1'})):
        print('API 地址必须使用 HTTPS；仅本机地址允许 HTTP。', file=sys.stderr)
        return 2
    params = {k: v for k, v in vars(args).items() if k not in {
        'base', 'command', 'contact_id', 'message_id', 'output'} and v is not None}
    path = args.command
    if path == 'scorecard':
        path = f'contacts/{quote(args.contact_id, safe="")}/scorecard'
    elif path == 'attachment':
        path = f'messages/{args.message_id}/attachment'
    target = f'{base}/{path}' + ('?' + urlencode(params) if params else '')
    request = Request(target, headers={'Authorization': f'Bearer {key}', 'Accept':'application/json'})
    created = False
    try:
        with build_opener(NoRedirect).open(request, timeout=60) as response:
            if args.command == 'attachment':
                # Exclusive creation prevents accidental replacement of user files.
                with args.output.open('xb') as output:
                    created = True
                    while chunk := response.read(65536):
                        output.write(chunk)
                print(json.dumps({'saved_to': str(args.output.resolve())}, ensure_ascii=False))
            else:
                payload = json.load(response)
                print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    except HTTPError as error:
        print(f'API 请求失败：HTTP {error.code}。请检查权限、参数、额度或服务状态。', file=sys.stderr)
        error.close()
    except (URLError, OSError, ValueError):
        print('连接、响应或文件写入失败；请检查服务地址和输出路径（文件不得已存在）。', file=sys.stderr)
    if created:
        args.output.unlink(missing_ok=True)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
