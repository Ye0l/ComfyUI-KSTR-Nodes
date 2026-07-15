MAX_TEXT_CONCAT_INPUTS = 64


class NormalizeCommaPrompt:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": (
                    "STRING",
                    {
                        "multiline": True,
                        "dynamicPrompts": True,
                        "default": "",
                    },
                ),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("prompt",)
    FUNCTION = "normalize"
    CATEGORY = "Yeol/Prompt"

    def normalize(self, prompt: str):
        uncommented_prompt = "\n".join(
            line for line in prompt.splitlines() if not line.lstrip().startswith("//")
        )
        normalized_parts = (
            part.strip() for part in uncommented_prompt.split(",") if part.strip()
        )
        return (", ".join(normalized_parts),)


class TextConcatenate:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "separator": (
                    "STRING",
                    {
                        "default": ", ",
                        "multiline": False,
                    },
                ),
                "strip_inputs": ("BOOLEAN", {"default": True}),
                "skip_empty": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                f"text_{index}": ("STRING", {"forceInput": True})
                for index in range(1, MAX_TEXT_CONCAT_INPUTS + 1)
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "concatenate"
    CATEGORY = "Yeol/Text"

    def concatenate(
        self,
        separator: str,
        strip_inputs: bool,
        skip_empty: bool,
        **kwargs,
    ):
        indexed_values = []
        for name, value in kwargs.items():
            if not name.startswith("text_"):
                continue

            try:
                index = int(name.removeprefix("text_"))
            except ValueError:
                continue

            indexed_values.append((index, value))

        parts = []
        for _, value in sorted(indexed_values):
            if value is None:
                value = ""
            elif not isinstance(value, str):
                value = str(value)

            if strip_inputs:
                value = value.strip()
            if skip_empty and not value:
                continue

            parts.append(value)

        return (separator.join(parts),)


NODE_CLASS_MAPPINGS = {
    "YeolNormalizeCommaPrompt": NormalizeCommaPrompt,
    "YeolTextConcatenate": TextConcatenate,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "YeolNormalizeCommaPrompt": "Normalize Comma Prompt",
    "YeolTextConcatenate": "Text Concatenate (Dynamic)",
}
