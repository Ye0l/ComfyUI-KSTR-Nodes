class LoRARatioStacker:
    """
    LORA_STACK 안의 strength를 비율로 해석하여 지정한 합계 강도로 정규화한다.

    ComfyUI-Lora-Manager 호환 형식:
        [(lora_path, model_strength, clip_strength), ...]
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "lora_stack": ("LORA_STACK",),
                "total_strength": (
                    "FLOAT",
                    {
                        "default": 1.0,
                        "min": -100.0,
                        "max": 100.0,
                        "step": 0.01,
                    },
                ),
                "ratio_source": (
                    [
                        "model strength",
                        "clip strength",
                        "separate model / clip",
                    ],
                    {
                        "default": "model strength",
                    },
                ),
            }
        }

    RETURN_TYPES = ("LORA_STACK", "STRING")
    RETURN_NAMES = ("lora_stack", "applied_ratios")
    FUNCTION = "normalize"
    CATEGORY = "Yeol/LoRA"

    def normalize(self, lora_stack, total_strength, ratio_source):
        if not lora_stack:
            return ([], "No LoRA in stack")

        parsed = []
        for index, entry in enumerate(lora_stack):
            if not isinstance(entry, (list, tuple)) or len(entry) < 3:
                raise ValueError(
                    f"LORA_STACK entry {index + 1} must be "
                    "(lora_path, model_strength, clip_strength)"
                )

            lora_path = entry[0]
            model_ratio = float(entry[1])
            clip_ratio = float(entry[2])
            parsed.append((lora_path, model_ratio, clip_ratio))

        output = []
        lines = []

        if ratio_source == "separate model / clip":
            model_sum = sum(abs(model_ratio) for _, model_ratio, _ in parsed)
            clip_sum = sum(abs(clip_ratio) for _, _, clip_ratio in parsed)

            for lora_path, model_ratio, clip_ratio in parsed:
                model_strength = (
                    float(total_strength) * model_ratio / model_sum
                    if model_sum > 0
                    else 0.0
                )
                clip_strength = (
                    float(total_strength) * clip_ratio / clip_sum
                    if clip_sum > 0
                    else 0.0
                )

                output.append(
                    (lora_path, model_strength, clip_strength)
                )
                lines.append(
                    f"{lora_path}: "
                    f"model={model_strength:.6g}, "
                    f"clip={clip_strength:.6g}"
                )

            lines.append(
                f"model_ratio_sum={model_sum:.6g}, "
                f"clip_ratio_sum={clip_sum:.6g}, "
                f"total_strength={float(total_strength):.6g}"
            )

        else:
            use_clip = ratio_source == "clip strength"
            ratios = [
                clip_ratio if use_clip else model_ratio
                for _, model_ratio, clip_ratio in parsed
            ]
            ratio_sum = sum(abs(ratio) for ratio in ratios)

            if ratio_sum <= 0:
                return ([], "Ratio sum is zero; no LoRA applied")

            for (lora_path, _, _), ratio in zip(parsed, ratios):
                strength = float(total_strength) * ratio / ratio_sum
                output.append((lora_path, strength, strength))
                lines.append(
                    f"{lora_path}: ratio={ratio:.6g}, "
                    f"model={strength:.6g}, clip={strength:.6g}"
                )

            lines.append(
                f"ratio_sum={ratio_sum:.6g}, "
                f"total_strength={float(total_strength):.6g}"
            )

        return (output, "\n".join(lines))


NODE_CLASS_MAPPINGS = {
    "YeolLoRARatioStacker": LoRARatioStacker,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "YeolLoRARatioStacker": "LoRA Ratio Stacker",
}
