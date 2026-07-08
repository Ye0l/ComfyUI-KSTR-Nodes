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
