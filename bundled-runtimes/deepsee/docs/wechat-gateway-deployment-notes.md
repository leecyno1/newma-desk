# WeChat Gateway deployment notes

This note captures operational lessons from deploying Deepsee with wechatapi.net and Hermes Agent on a public Linux server.

## Baseline topology

```text
WeChat user
  -> wechatapi.net iPad protocol
  -> http://<server_public_ip>:8001/api/wechat-gateway/callback
  -> Deepsee FastAPI
  -> Hermes API Server http://127.0.0.1:8642/v1/chat/completions
```

Use the same model provider configuration for Deepsee AI routes and Hermes fallback/delegation routes when possible. For MiniMax China deployments, keep the OpenAI-compatible base URL normalized to a single `/v1` suffix.

## Public callback binding

wechatapi.net must be able to reach the callback URL from the public Internet. If Deepsee listens only on `127.0.0.1`, callback binding may fail with:

```text
push msg err
502 Bad Gateway
```

For direct-public-IP deployments, set Deepsee to listen on all interfaces:

```env
HOST=0.0.0.0
PORT=8001
```

Then restart Deepsee and verify both local and public reachability:

```bash
curl http://127.0.0.1:8001/api/health
curl http://<server_public_ip>:8001/api/health
curl -X POST http://<server_public_ip>:8001/api/wechat-gateway/callback \
  -H 'Content-Type: application/json' \
  -d '{"probe": true}'
```

The callback probe should return HTTP 200. A payload without a valid WeChat event may return `ignored_event`; that is fine for reachability testing.

Bind or rebind the callback after login and after confirming public reachability:

```bash
curl -X POST http://127.0.0.1:8001/api/wechat-gateway/bind-callback
```

Expected successful result includes the callback URL and a wechatapi response like `{"ret":200,"msg":"操作成功"}`.

## Persist login state for second login

After WeChatAPI login succeeds, save the durable device mapping:

- `token`
- `app_id`
- `wxid`
- `nick_name`
- `region_id`
- `device_type`
- `callback_public_url`

Recommended local path:

```text
data/wechat_login_state.json
```

Set it to owner-only permissions:

```bash
chmod 600 data/wechat_login_state.json
```

Use the saved `app_id` for subsequent QR login requests. Only pass an empty `appId` when WeChatAPI reports that the saved device no longer exists.

Example shape, with token redacted here:

```json
{
  "provider": "wechatapi.net",
  "base_url": "http://api.wechatapi.net/finder/v2/api",
  "header_name": "VideosApi-token",
  "token": "<redacted>",
  "app_id": "wx_xxx",
  "wxid": "wxid_xxx",
  "nick_name": "...",
  "region_id": "110000",
  "device_type": "ipad",
  "callback_public_url": "http://<server_public_ip>:8001/api/wechat-gateway/callback",
  "online": true,
  "last_login_status": "success"
}
```

## Login verification notes

For the observed wechatapi.net iPad flow:

- Use `regionId: "110000"`.
- Use `type: "ipad"`.
- Use `/login/checkLogin` exactly; lower-case `/login/checklogin` may return 404 on the active API base.
- Treat `ret=200` alone as insufficient.
- `data.status=0`: waiting for scan.
- `data.status=1`: scanned, waiting for confirmation or new-device verification.
- `data.status=2` or non-empty `data.loginInfo`: final login success.
- For new-device face verification, `autoSliding: false` can surface `data.url`, an authentication QR URL. Give that QR to the user for the iOS verification app, then continue polling.

## Runtime checks

Check online state:

```bash
curl -X POST http://api.wechatapi.net/finder/v2/api/login/checkOnline \
  -H 'VideosApi-token: <token>' \
  -H 'Content-Type: application/json' \
  -d '{"appId":"<app_id>"}'
```

Expected:

```json
{"ret":200,"msg":"操作成功","data":true}
```

Check gateway config:

```bash
curl http://127.0.0.1:8001/api/wechat-gateway/config
```

Check whether callbacks are arriving:

```bash
tail -f uvicorn.log | grep wechat-gateway/callback
```

Check message ingestion in SQLite:

```bash
sqlite3 data/app.db 'select id, chat_id, direction, type, substr(content_text,1,80) from messages order by id desc limit 10;'
```

## Subsession behavior

`sessionized_reply_enabled=true` alone does not create fixed WeChat subsessions. In the current implementation, `resolve_gateway_subsession()` only creates/uses a subsession when both are true:

```json
{
  "sessionized_reply_enabled": true,
  "fixed_subsession_enabled": true,
  "fixed_subsession_id": "<stable-id>"
}
```

If `fixed_subsession_enabled=false`, incoming callbacks can still be stored in `messages`, but `wechat_subsessions`, `wechat_subsession_memberships`, and `wechat_subsession_turns` remain empty and message metadata will have `subsession: null`.

## Known non-blocking health warning

`/api/ready` may report degraded with `CHATLOG-HTTP-001` when Chatlog is not running on `127.0.0.1:5030`. That does not prevent WeChatAPI callback binding or message ingestion, but features that depend on Chatlog history will be unavailable until Chatlog is started.
