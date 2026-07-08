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
        parts = [part.strip() for part in prompt.split(",")]
        return (", ".join(parts),)


NODE_CLASS_MAPPINGS = {
    "YeolNormalizeCommaPrompt": NormalizeCommaPrompt,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "YeolNormalizeCommaPrompt": "Normalize Comma Prompt",
}
