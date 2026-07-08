# ComfyUI-Yeol-Utils

## LoRA Ratio Stacker

`ComfyUI-Lora-Manager`의 `Lora Stacker (LoraManager)`와 직접 연결하는 비율 정규화 노드입니다.

### 연결

```text
Lora Stacker (LoraManager)
        LORA_STACK
             │
             ▼
     LoRA Ratio Stacker
             │
             ▼
Lora Loader (LoraManager)
```

Lora Manager Stacker의 strength 칸에는 실제 강도가 아니라 **비율**을 입력합니다.

예:

```text
Lora Manager Stacker:
A strength = 5
B strength = 3
C strength = 2

LoRA Ratio Stacker:
total_strength = 1.2
ratio_source = model strength
```

출력:

```text
A = 0.60
B = 0.36
C = 0.24
합계 = 1.20
```

## 입출력

입력:

- `lora_stack`: `LORA_STACK`
- `total_strength`: 정규화 후 강도 합계
- `ratio_source`
  - `model strength`: 각 항목의 model strength를 단일 비율로 사용
  - `clip strength`: 각 항목의 clip strength를 단일 비율로 사용
  - `separate model / clip`: model과 clip 비율을 각각 독립적으로 정규화

출력:

- `lora_stack`: Lora Manager와 동일한 `LORA_STACK`
- `applied_ratios`: 계산 결과 확인용 문자열

## 호환성

출력 형식:

```python
[
    (lora_path, model_strength, clip_strength),
    ...
]
```

따라서 다음에 연결할 수 있습니다.

- `Lora Loader (LoraManager)`
- `LoRA Text Loader (LoraManager)`
- 동일한 `LORA_STACK` 튜플 형식을 사용하는 다른 커스텀 노드

슬라이더 LoRA는 별도 Loader를 이 노드 앞이나 뒤에 배치할 수 있습니다.
이 노드는 MODEL/CLIP을 직접 수정하지 않고 스택 데이터만 변환합니다.
