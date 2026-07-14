# ComfyUI-KSTR-Nodes

ComfyUI에서 쓰는 간단한 유틸 노드 모음입니다.

## 설치

`custom_nodes/ComfyUI-KSTR-Nodes`에 넣고 ComfyUI를 재시작하면 됩니다.

### 로컬 프롬프트 모델 사용

`Korean Image Prompt (EXAONE)` 노드는 별도 LLM 의존성이 필요합니다.

```bash
cd custom_nodes/ComfyUI-KSTR-Nodes
pip install -r requirements-llm.txt
```

모델은 `KSTR_PROMPT_MODEL` 환경변수로 지정합니다. Hugging Face 모델 ID와 로컬 디렉터리를 모두 사용할 수 있습니다.

```bash
export KSTR_PROMPT_MODEL=/models/EXAONE-3.5-2.4B-Instruct
```

환경변수가 없으면 `LGAI-EXAONE/EXAONE-3.5-2.4B-Instruct`를 사용합니다. 최초 실행 시 Hugging Face에서 모델을 내려받을 수 있습니다.

EXAONE 모델은 코드와 별개의 라이선스를 사용하므로 모델 사용 전 [EXAONE AI Model License](https://huggingface.co/LGAI-EXAONE/EXAONE-3.5-2.4B-Instruct)를 확인하세요.

## 노드 목록

| Node | 용도 | 핵심 입력 | 출력 |
| --- | --- | --- | --- |
| Normalize Comma Prompt | 쉼표 기준 프롬프트 공백 정리 | `prompt` | 정리된 `STRING` |
| Korean Image Prompt (EXAONE) | 한국어 자연어를 로컬 EXAONE으로 이미지 프롬프트화 | `description`, `prompt_format`, `creativity` | positive / negative `STRING` |
| LoRA Ratio Stacker | `LORA_STACK` 비율을 지정 합계 강도로 재분배 | `lora_stack`, `total_strength`, `ratio_source` | 재계산된 `LORA_STACK`, `applied_ratios` |
| Image to WEBP | `IMAGE` 배치를 WEBP로 변환 | `image`, `quality`, `method`, `lossless`, 메타데이터 옵션 | `WEBP` |
| Send WEBP to Telegram | WEBP를 Telegram Bot API로 전송 | `webp`, `bot_token`, `chat_id`, `caption`, `send_as_document` | 원본 `WEBP`, 응답 문자열 |
| POST WEBP to Immich | WEBP를 Immich `/api/assets`로 업로드 | `webp`, `api_url`, `api_key`, `device_id` | 원본 `WEBP`, 응답 문자열 |

## 사용 예시

### Normalize Comma Prompt

입력:

```text
masterpiece, 1girl , blue hair,  smile
```

출력:

```text
masterpiece, 1girl, blue hair, smile
```

### Korean Image Prompt (EXAONE)

입력:

```text
비 오는 밤 골목에서 검은 교복을 입은 여학생이 우산을 들고 뒤돌아본다.
네온사인이 젖은 바닥에 반사되고 약간 불안한 분위기다.
```

주요 옵션:

- `prompt_format`: `anime_tags`, `natural_language`, `hybrid`
- `creativity`: `strict`, `balanced`, `creative`
- `keep_model_loaded`: 다음 실행을 위해 모델을 VRAM에 유지할지 선택
- `style_prefix`: 반드시 반영할 스타일 또는 접두 프롬프트
- `negative_hint`: 사용자가 직접 지정할 네거티브 힌트

출력 예:

```text
positive_prompt:
1girl, black school uniform, holding umbrella, looking back, rainy night,
narrow alley, neon signs, wet pavement, neon reflections, uneasy atmosphere

negative_prompt:
low detail, visual artifacts, text, watermark
```

`<lora:name:0.8>`, `(tag:1.2)`, `[tag:0.8]`, `__wildcard__`, `{red|blue}` 형식은 변환 중 보호한 뒤 원문 그대로 복원합니다.

### LoRA Ratio Stacker

입력:

```text
Lora Stacker (LoraManager)
- A strength = 5
- B strength = 3
- C strength = 2

LoRA Ratio Stacker
- total_strength = 1.2
- ratio_source = model strength
```

출력:

```text
A = 0.60
B = 0.36
C = 0.24
합계 = 1.20
```

연결:

```text
Lora Stacker (LoraManager)
        ↓
LoRA Ratio Stacker
        ↓
Lora Loader (LoraManager)
```

### Image to WEBP

예:

```text
VAE Decode / Load Image
        ↓
Image to WEBP

- quality = 95
- method = 6
- lossless = false
- embed_metadata = true
- filename_prefix = comfyui
```

출력된 `WEBP`는 아래 Telegram / Immich 노드에 바로 연결하면 됩니다.

`embed_metadata`가 켜져 있으면 `prompt` / `workflow` / 커스텀 메타데이터를 ComfyUI가 PNG에 쓰는 것과 동일한 방식(EXIF)으로 WEBP에 심습니다. Immich에 업로드한 뒤 원본을 다시 받아 ComfyUI에 드래그해도 워크플로우가 복원됩니다.

### Send WEBP to Telegram

연결:

```text
Image to WEBP
        ↓
Send WEBP to Telegram
```

예시 입력:

```text
bot_token = YOUR_TELEGRAM_BOT_TOKEN
chat_id = YOUR_CHAT_ID
caption = render sample
send_as_document = true
```

### POST WEBP to Immich

연결:

```text
Image to WEBP
        ↓
POST WEBP to Immich
```

예시 입력:

```text
api_url = http://127.0.0.1:2283/api/assets
api_key = YOUR_IMMICH_API_KEY
device_id = comfyui-kstr
filename_prefix_override = render
is_favorite = false
```

각 WEBP는 Immich `assetData`로 업로드되고, `deviceAssetId`, `fileCreatedAt`, `fileModifiedAt`는 노드가 자동으로 채웁니다.
