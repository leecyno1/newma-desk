# QVeris REST API Reference

This reference is based on the frozen Vibe-Trading QVeris contract dated
2026-07-07. API authentication uses `Authorization: Bearer <QVERIS_API_KEY>`.
The default base endpoint is the QVeris API v1 base configured by
`QVERIS_BASE_URL`; Vibe-Trading's default is the production API v1 endpoint from
the frozen contract.

## Common Fields

| Field | Type | Meaning |
|-------|------|---------|
| `session_id` | string? | Optional caller session for usage grouping. |
| `search_id` | string? | Search correlation id returned by `/search`. |
| `remaining_credits` | number? | Account credits after the request or latest free lookup. |
| `error_message` | string? | Provider or API error text. Treat as user-facing diagnostic, not a stack trace. |

Errors may appear as HTTP errors or as HTTP 200 responses with
`success=false`, `error_message`, and an execution/billing outcome. Parse both.

## POST `/search` (Free)

Searches the marketplace for matching capabilities. Invalid keys return HTTP
401 with empty results.

### Request

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `query` | string | yes | Natural-language capability query. |
| `limit` | integer | no | 1-100, default 20. |
| `session_id` | string | no | Optional Vibe-Trading session id. |

### Response

| Field | Type | Notes |
|-------|------|-------|
| `query` | string | Echoed query. |
| `search_id` | string | Pass to inspect/execute for attribution. |
| `total` | integer | Total matched capabilities. |
| `results` | array | Capability summaries, see below. |
| `elapsed_time_ms` | number | Search latency. |
| `remaining_credits` | number? | Current balance if returned. |
| `error_message` | string? | Present on degraded/error response. |

### Result Object

| Field | Type | Notes |
|-------|------|-------|
| `tool_id` | string | Required for inspect/execute. |
| `name` | string | Capability display name. |
| `description` | string | Capability summary. |
| `provider_name` | string? | Provider/vendor name. |
| `params` | array | Parameter summaries with `name`, `type`, `required`, `description`, optional `enum`. |
| `examples.sample_parameters` | object? | Example request parameters. |
| `expected_cost` | string | Quoted expected credit cost; compare before execute. |
| `billing_rule` | object | Billing terms; preserve for user-visible cost quotes. |
| `stats` | object | Includes `avg_execution_time_ms`, `success_rate`, and provider stats when present. |
| `categories` | array | Category objects, usually with `slug`. |

## POST `/tools/by-ids` (Free)

Fetches full capability metadata by `tool_id`. Use this before paid execution.

### Request

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `tool_ids` | string[] | yes | One or more ids returned by search. |
| `search_id` | string | no | Original search correlation id. |
| `session_id` | string | no | Optional Vibe-Trading session id. |

### Response

The response uses the same `results` shape as `/search`, but with fuller
`params` and examples. Treat missing fields as absent, not fatal.

## POST `/tools/execute?tool_id={tool_id}` (Paid When Billable)

Executes one capability. Vibe-Trading must keep QVeris unavailable in `free`
mode and check session budget in `paid` mode before sending the request.

### Query

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `tool_id` | string | yes | Capability id from search/inspect. |

### Request Body

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `search_id` | string | no | Correlates execution to discovery. |
| `session_id` | string | no | Correlates execution to Vibe-Trading session. |
| `model` | string | no | Optional model hint accepted by QVeris. |
| `parameters` | object | yes | Exact parameters from inspected schema. |
| `max_response_size` | integer | no | Default 20480; `-1` requests no truncation. |

### Response

| Field | Type | Notes |
|-------|------|-------|
| `execution_id` | string | Use for usage reconciliation. |
| `result` | object | Provider payload or truncation envelope. |
| `success` | boolean | Provider/API success. |
| `error_message` | string? | Error when `success=false`. |
| `execution_time` | number? | Provider execution time. |
| `elapsed_time_ms` | number? | End-to-end latency. |
| `billing.summary` | string? | Human billing summary. |
| `billing.list_amount_credits` | number? | Listed credit amount. |
| `execution_outcome.outcome` | string? | Execution outcome label. |
| `execution_outcome.reason_code` | string? | Reason for charge or no-charge state. |
| `execution_outcome.provider_success` | boolean? | Whether upstream provider succeeded. |
| `execution_outcome.billable_success` | boolean? | Whether success is billable. |
| `execution_outcome.result_valid` | boolean? | Whether result passed QVeris validation. |
| `execution_outcome.status` | string? | Settlement status such as `not_charged`. |
| `cost` | number | Actual charged credits; observed parameter errors return `0.0`. |
| `remaining_credits` | number | Balance after settlement. |

### Truncation Envelope

When the provider payload exceeds `max_response_size`, `result` contains:

| Field | Type | Notes |
|-------|------|-------|
| `message` | string | Explains the response is too long. |
| `full_content_file_url` | string | Signed URL for the full JSON payload. |
| `truncated_content` | string/object | Partial payload for quick inspection. |

Fetch `full_content_file_url` only when the full result is necessary. Signed
URLs may expire and should not be persisted as durable evidence.

## GET `/auth/usage/history/v2` (Free)

Usage event history and summary endpoint. The response shape is intentionally
parsed leniently because QVeris may return events at the top level or under
`data`.

### Query Parameters

| Parameter | Type | Notes |
|-----------|------|-------|
| `execution_id` | string | Filter one execution. |
| `start_date`, `end_date` | string | Date range filters. |
| `kind` | string | Common values: `discover`, `call`, `model`. |
| `charge_outcome` | string | `charged`, `included`, `failed_not_charged`, `failed_charged_review`. |
| `summary` | boolean | `true` for aggregate summary. |
| `bucket` | string | Common value: `day`. |
| `limit` | integer | Max rows. |
| `page`, `page_size` | integer | Pagination. |

### Event Fields

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | Usage event id. |
| `event_type` | string | Event category. |
| `session_id` | string? | Caller session. |
| `search_id` | string? | Search id. |
| `execution_id` | string? | Execution id. |
| `tool_id` | string? | Capability id. |
| `success` | boolean? | Request success. |
| `charge_outcome` | string? | Settlement result. |
| `duration_ms` | number? | Duration in milliseconds. |

## GET `/auth/credits/ledger` (Free)

Credit ledger endpoint for balance and audit.

### Query Parameters

| Parameter | Type | Notes |
|-----------|------|-------|
| `direction` | string | `consume`, `grant`, or `any`. |
| `entry_type` | string | Ledger entry type filter. |
| `summary` | boolean | `true` for aggregate summary. |
| `limit` | integer | Max rows. |
| `page`, `page_size` | integer | Pagination. |

### Item Fields

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | Ledger entry id. |
| `entry_type` | string | Examples: `consume_tool_execute`, `grant_welcome_bonus`. |
| `amount_credits` | number | Negative means consumption; positive means grant. |
| `execution_id` | string? | Execution id for consumed credits. |
| `pre_settlement_bill` | object? | Bill details before settlement. |

## Charge Outcomes and Reason Codes

| Field/value | Meaning | Agent behavior |
|-------------|---------|----------------|
| `charge_outcome=charged` | Credits were consumed. | Report `cost` and `remaining_credits`. |
| `charge_outcome=included` | Included/free quota covered it. | Report no incremental charge if `cost=0`. |
| `charge_outcome=failed_not_charged` | Failure was not charged. | Surface error and suggest parameter/provider fix. |
| `charge_outcome=failed_charged_review` | Failure may need billing review. | Preserve `execution_id` and tell user to review usage. |
| `reason_code=missing_required_parameter` | Parameters invalid or missing. | Inspect schema, repair parameters, no charge expected. |
| `reason_code=empty_result` | Provider returned no usable data. | No charge expected; try different date/symbol/provider. |
| `reason_code=provider_error` | Upstream provider failed. | No charge expected; try alternate provider. |
| unknown `reason_code` | QVeris may add values. | Treat as opaque evidence; do not infer charge beyond `cost`. |

## 429 Rate Limits

Contracted nominal limits are search 120/min and execute 200/min, but measured
bursts around 20 requests in a short window can return 429. Clients must throttle
requests and retry 429 responses using headers.

| Header | Required handling |
|--------|-------------------|
| `Retry-After` | Sleep for the indicated seconds before retry. |
| `X-RateLimit-*` | If present, log only redacted/non-secret values and respect reset hints. |

Vibe-Trading clients should use a minimum request interval of 0.5 seconds and at
most 3 retries on 429.
