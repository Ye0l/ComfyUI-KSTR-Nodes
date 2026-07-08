# ComfyUI-KSTR-Nodes

ComfyUI에서 쓰는 간단한 유틸 노드 모음입니다.

## 설치

`custom_nodes/ComfyUI-KSTR-Nodes`에 넣고 ComfyUI를 재시작하면 됩니다.

## 노드 목록

| Node | 용도 | 핵심 입력 | 출력 |
| --- | --- | --- | --- |
| Normalize Comma Prompt | 쉼표 기준 프롬프트 공백 정리 | `prompt` | 정리된 `STRING` |
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

### Send WEBP to Telegram

연결:

```text
Image to WEBP
        ↓
Send WEBP to Telegram
```

예시 입력:

```text
bot_token = 123456:ABC...
chat_id = 123456789
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
api_key = your-immich-api-key
device_id = comfyui-kstr
filename_prefix_override = render
is_favorite = false
```

각 WEBP는 Immich `assetData`로 업로드되고, `deviceAssetId`, `fileCreatedAt`, `fileModifiedAt`는 노드가 자동으로 채웁니다.
