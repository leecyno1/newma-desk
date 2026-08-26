#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
library_dir="${IMA_RESEARCH_LIBRARY_DIR:-$project_root/ima知识库}"
knowledge_base_name="${IMA_KNOWLEDGE_BASE_NAME:-ima知识库}"
knowledge_root_folder_name="${IMA_KNOWLEDGE_ROOT_FOLDER_NAME:-$knowledge_base_name}"
ima_skill_dir="${IMA_SKILL_DIR:-$HOME/.codex/skills/ima-skill}"
ima_api="$ima_skill_dir/ima_api.cjs"
preflight="$ima_skill_dir/knowledge-base/scripts/preflight-check.cjs"
cos_upload="$ima_skill_dir/knowledge-base/scripts/cos-upload.cjs"
client_id_file="${IMA_CLIENT_ID_FILE:-$HOME/.config/ima/client_id}"
api_key_file="${IMA_API_KEY_FILE:-$HOME/.config/ima/api_key}"

for command_name in node jq; do
  command -v "$command_name" >/dev/null || {
    echo "缺少依赖：$command_name" >&2
    exit 1
  }
done

for required_file in "$ima_api" "$preflight" "$cos_upload"; do
  [[ -f "$required_file" ]] || {
    echo "未找到 IMA 同步组件：$required_file" >&2
    exit 1
  }
done

client_id="${IMA_OPENAPI_CLIENTID:-}"
api_key="${IMA_OPENAPI_APIKEY:-}"

if [[ -z "$client_id" ]]; then
  [[ -f "$client_id_file" ]] || {
    echo "未找到 IMA Client ID：请设置 IMA_OPENAPI_CLIENTID 或配置 $client_id_file" >&2
    exit 1
  }
  client_id="$(tr -d '\r\n' < "$client_id_file")"
fi

if [[ -z "$api_key" ]]; then
  [[ -f "$api_key_file" ]] || {
    echo "未找到 IMA API Key：请设置 IMA_OPENAPI_APIKEY 或配置 $api_key_file" >&2
    exit 1
  }
  api_key="$(tr -d '\r\n' < "$api_key_file")"
fi

ima_options=$(jq -nc \
  --arg clientId "$client_id" \
  --arg apiKey "$api_key" \
  '{clientId:$clientId,apiKey:$apiKey}')

[[ -d "$library_dir" ]] || {
  echo "本地纪要目录不存在：$library_dir" >&2
  exit 1
}

files=()
while IFS= read -r -d '' file_path; do
  files+=("$file_path")
done < <(
  find "$library_dir" -type f \
    \( -iname '*.pdf' -o -iname '*.docx' -o -iname '*.pptx' -o -iname '*.md' -o -iname '*.txt' \) \
    -print0
)

if [[ ${#files[@]} -eq 0 ]]; then
  echo "本地纪要库已就绪，当前没有可同步文件。"
  exit 0
fi

api_call() {
  local api_path="$1"
  local body="$2"
  local response message code attempt
  for attempt in 1 2 3 4; do
    if ! response=$(node "$ima_api" "$api_path" "$body" "$ima_options"); then
      return 1
    fi
    code=$(jq -r '.code // -1' <<<"$response")
    [[ "$code" == "0" ]] && {
      printf '%s' "$response"
      return 0
    }
    message=$(jq -r '.msg // "IMA API 调用失败"' <<<"$response")
    if [[ "$code" == "110021" || "$message" == *"请求频控"* ]]; then
      sleep "$attempt"
      continue
    fi
    echo "$message" >&2
    [[ "$message" == *"请求超量"* ]] && return 75
    return 1
  done
  echo "IMA 请求过快，请稍后重试。" >&2
  return 1
}

search_body=$(jq -nc --arg query "$knowledge_base_name" \
  '{query:$query,cursor:"",limit:20}')
search_response=$(api_call openapi/wiki/v1/search_knowledge_base "$search_body")
knowledge_base_id=$(jq -r --arg name "$knowledge_base_name" \
  '.data.info_list[]? | select((.kb_name // .name) == $name) | (.kb_id // .id)' <<<"$search_response" | head -n 1)

if [[ -z "$knowledge_base_id" ]]; then
  echo "IMA 中尚未找到知识库「${knowledge_base_name}」，请先在 IMA 客户端创建。" >&2
  exit 1
fi

root_list_body=$(jq -nc --arg knowledge_base_id "$knowledge_base_id" \
  '{knowledge_base_id:$knowledge_base_id,cursor:"",limit:50}')
root_list_response=$(api_call openapi/wiki/v1/get_knowledge_list "$root_list_body")
knowledge_root_folder_id=$(jq -r --arg name "$knowledge_root_folder_name" \
  '.data.knowledge_list[]? | select(.media_type == 99 and .title == $name) | .media_id' \
  <<<"$root_list_response" | head -n 1)

if [[ -z "$knowledge_root_folder_id" ]]; then
  echo "IMA 知识库「${knowledge_base_name}」中未找到文件夹「${knowledge_root_folder_name}」。" >&2
  exit 1
fi

folder_paths=("")
folder_ids=("$knowledge_root_folder_id")
resolved_folder_id=""

resolve_remote_folder() {
  local relative_dir="$1"
  local current_folder_id="$knowledge_root_folder_id"
  local current_path=""
  local part cached_id folder_body folder_response child_folder_id
  local index
  local parts=()

  if [[ -z "$relative_dir" || "$relative_dir" == "." ]]; then
    resolved_folder_id="$knowledge_root_folder_id"
    return 0
  fi

  IFS='/' read -r -a parts <<<"$relative_dir"
  for part in "${parts[@]}"; do
    current_path="${current_path:+$current_path/}$part"
    cached_id=""
    for ((index = 0; index < ${#folder_paths[@]}; index += 1)); do
      if [[ "${folder_paths[$index]}" == "$current_path" ]]; then
        cached_id="${folder_ids[$index]}"
        break
      fi
    done

    if [[ -n "$cached_id" ]]; then
      current_folder_id="$cached_id"
      continue
    fi

    folder_body=$(jq -nc \
      --arg knowledge_base_id "$knowledge_base_id" \
      --arg folder_id "$current_folder_id" \
      '{knowledge_base_id:$knowledge_base_id,folder_id:$folder_id,cursor:"",limit:50}')
    folder_response=$(api_call openapi/wiki/v1/get_knowledge_list "$folder_body") || return 1
    child_folder_id=$(jq -r --arg name "$part" \
      '.data.knowledge_list[]? | select(.media_type == 99 and .title == $name) | .media_id' \
      <<<"$folder_response" | head -n 1)

    if [[ -z "$child_folder_id" ]]; then
      echo "IMA 中缺少目录：${knowledge_root_folder_name}/${current_path}。" >&2
      return 1
    fi

    folder_paths+=("$current_path")
    folder_ids+=("$child_folder_id")
    current_folder_id="$child_folder_id"
  done

  resolved_folder_id="$current_folder_id"
}

uploaded=0
skipped=0
failed=0
quota_exhausted=0
file_records=()

for file_path in "${files[@]}"; do
  relative_path="${file_path#"$library_dir"/}"
  relative_dir="$(dirname "$relative_path")"
  [[ "$relative_dir" == "." ]] && relative_dir=""

  if ! resolve_remote_folder "$relative_dir"; then
    ((failed += 1))
    continue
  fi

  if ! preflight_response=$(node "$preflight" --file "$file_path"); then
    reason=$(jq -r '.reason // "文件不受支持"' <<<"${preflight_response:-{}}")
    echo "跳过 $(basename "$file_path")：$reason" >&2
    ((failed += 1))
    continue
  fi

  file_name=$(jq -r '.file_name' <<<"$preflight_response")
  file_ext=$(jq -r '.file_ext' <<<"$preflight_response")
  file_size=$(jq -r '.file_size' <<<"$preflight_response")
  media_type=$(jq -r '.media_type' <<<"$preflight_response")
  content_type=$(jq -r '.content_type' <<<"$preflight_response")

  file_records+=("$(jq -nc \
    --arg file_path "$file_path" \
    --arg file_name "$file_name" \
    --arg file_ext "$file_ext" \
    --arg content_type "$content_type" \
    --arg folder_id "$resolved_folder_id" \
    --argjson file_size "$file_size" \
    --argjson media_type "$media_type" \
    '{file_path:$file_path,file_name:$file_name,file_ext:$file_ext,file_size:$file_size,media_type:$media_type,content_type:$content_type,folder_id:$folder_id}')")
done

if [[ ${#file_records[@]} -eq 0 ]]; then
  echo "没有可同步的受支持文件。"
  [[ $failed -eq 0 ]]
  exit
fi

duplicate_results='[]'
while IFS= read -r folder_id; do
  duplicate_body=$(printf '%s\n' "${file_records[@]}" | jq -sc \
    --arg knowledge_base_id "$knowledge_base_id" \
    --arg folder_id "$folder_id" \
    '{params:(map(select(.folder_id == $folder_id) | {name:.file_name,media_type:.media_type})),knowledge_base_id:$knowledge_base_id,folder_id:$folder_id}')
  if duplicate_response=$(api_call openapi/wiki/v1/check_repeated_names "$duplicate_body"); then
    duplicate_results=$(jq -nc \
      --argjson current "$duplicate_results" \
      --argjson incoming "$(jq '.data.results // []' <<<"$duplicate_response")" \
      --arg folder_id "$folder_id" \
      '$current + ($incoming | map(. + {folder_id:$folder_id}))')
  elif [[ $? -eq 75 ]]; then
    quota_exhausted=1
    break
  else
    exit 1
  fi
done < <(printf '%s\n' "${file_records[@]}" | jq -sr 'map(.folder_id) | unique[]')

for file_record in "${file_records[@]}"; do
  file_path=$(jq -r '.file_path' <<<"$file_record")
  file_name=$(jq -r '.file_name' <<<"$file_record")
  file_ext=$(jq -r '.file_ext' <<<"$file_record")
  file_size=$(jq -r '.file_size' <<<"$file_record")
  media_type=$(jq -r '.media_type' <<<"$file_record")
  content_type=$(jq -r '.content_type' <<<"$file_record")
  folder_id=$(jq -r '.folder_id' <<<"$file_record")

  [[ $quota_exhausted -eq 1 ]] && break
  is_repeated=$(jq -r \
    --arg folder_id "$folder_id" \
    --arg name "$file_name" \
    '[.[] | select(.folder_id == $folder_id and .name == $name)][0].is_repeated // false' \
    <<<"$duplicate_results")
  if [[ "$is_repeated" == "true" ]]; then
    ((skipped += 1))
    continue
  fi

  create_body=$(jq -nc \
    --arg file_name "$file_name" \
    --arg file_ext "$file_ext" \
    --arg content_type "$content_type" \
    --arg knowledge_base_id "$knowledge_base_id" \
    --argjson file_size "$file_size" \
    '{file_name:$file_name,file_size:$file_size,content_type:$content_type,knowledge_base_id:$knowledge_base_id,file_ext:$file_ext}')
  if create_response=$(api_call openapi/wiki/v1/create_media "$create_body"); then
    :
  elif [[ $? -eq 75 ]]; then
    quota_exhausted=1
    break
  else
    ((failed += 1))
    continue
  fi

  media_id=$(jq -r '.data.media_id' <<<"$create_response")
  credential=$(jq -c '.data.cos_credential' <<<"$create_response")
  cos_key=$(jq -r '.cos_key' <<<"$credential")

  if ! node "$cos_upload" \
    --file "$file_path" \
    --secret-id "$(jq -r '.secret_id' <<<"$credential")" \
    --secret-key "$(jq -r '.secret_key' <<<"$credential")" \
    --token "$(jq -r '.token' <<<"$credential")" \
    --bucket "$(jq -r '.bucket_name' <<<"$credential")" \
    --region "$(jq -r '.region' <<<"$credential")" \
    --cos-key "$cos_key" \
    --content-type "$content_type" \
    --start-time "$(jq -r '.start_time' <<<"$credential")" \
    --expired-time "$(jq -r '.expired_time' <<<"$credential")" \
    --timeout 300000; then
    ((failed += 1))
    continue
  fi

  add_body=$(jq -nc \
    --arg media_id "$media_id" \
    --arg title "$file_name" \
    --arg knowledge_base_id "$knowledge_base_id" \
    --arg folder_id "$folder_id" \
    --arg cos_key "$cos_key" \
    --arg file_name "$file_name" \
    --argjson media_type "$media_type" \
    --argjson file_size "$file_size" \
    '{media_type:$media_type,media_id:$media_id,title:$title,knowledge_base_id:$knowledge_base_id,folder_id:$folder_id,file_info:{cos_key:$cos_key,file_size:$file_size,file_name:$file_name}}')
  if api_call openapi/wiki/v1/add_knowledge "$add_body" >/dev/null; then
    echo "已同步：$file_name"
    ((uploaded += 1))
  elif [[ $? -eq 75 ]]; then
    quota_exhausted=1
    break
  else
    ((failed += 1))
  fi
done

echo "同步完成：新增 ${uploaded}，已存在 ${skipped}，失败 ${failed}。"
if [[ $quota_exhausted -eq 1 ]]; then
  echo "IMA 今日接口额度已用完；稍后再次运行会自动跳过已存在文件并继续同步。" >&2
  exit 75
fi
[[ $failed -eq 0 ]]
