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


NODE_CLASS_MAPPINGS = {
    "YeolNormalizeCommaPrompt": NormalizeCommaPrompt,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "YeolNormalizeCommaPrompt": "Normalize Comma Prompt",
}
