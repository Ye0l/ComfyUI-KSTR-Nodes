from .prompt_nodes import NODE_CLASS_MAPPINGS as PROMPT_NODE_CLASS_MAPPINGS
from .prompt_nodes import NODE_DISPLAY_NAME_MAPPINGS as PROMPT_NODE_DISPLAY_NAME_MAPPINGS
from . import local_prompt_nodes as _local_prompt_nodes
from .async_image_nodes import NODE_CLASS_MAPPINGS as IMAGE_NODE_CLASS_MAPPINGS
from .async_image_nodes import NODE_DISPLAY_NAME_MAPPINGS as IMAGE_NODE_DISPLAY_NAME_MAPPINGS
from .lora_nodes import NODE_CLASS_MAPPINGS as LORA_NODE_CLASS_MAPPINGS
from .lora_nodes import NODE_DISPLAY_NAME_MAPPINGS as LORA_NODE_DISPLAY_NAME_MAPPINGS

# Use an Apache-2.0 model by default. Users can override this with
# KSTR_PROMPT_MODEL using either a Hugging Face model ID or local path.
_local_prompt_nodes.DEFAULT_MODEL = "Qwen/Qwen3-1.7B"
_local_prompt_nodes.NODE_DISPLAY_NAME_MAPPINGS["YeolKoreanImagePrompt"] = (
    "Korean Image Prompt (Local LLM)"
)

# Qwen3 enables thinking mode by default. This task needs only the final JSON,
# so disable thinking when the selected tokenizer supports the option.
_original_load_prompt_model = _local_prompt_nodes.KoreanImagePrompt._load_model


@classmethod
def _load_prompt_model_without_thinking(cls):
    model, tokenizer, device = _original_load_prompt_model()

    if not getattr(tokenizer, "_kstr_apply_chat_template_wrapped", False):
        original_apply_chat_template = tokenizer.apply_chat_template

        def apply_chat_template(*args, **kwargs):
            model_source = cls._resolve_model_source()
            if model_source.startswith("Qwen/") or "qwen" in model_source.lower():
                kwargs.setdefault("enable_thinking", False)
            try:
                return original_apply_chat_template(*args, **kwargs)
            except TypeError:
                kwargs.pop("enable_thinking", None)
                return original_apply_chat_template(*args, **kwargs)

        tokenizer.apply_chat_template = apply_chat_template
        tokenizer._kstr_apply_chat_template_wrapped = True

    return model, tokenizer, device


_local_prompt_nodes.KoreanImagePrompt._load_model = _load_prompt_model_without_thinking

LOCAL_PROMPT_NODE_CLASS_MAPPINGS = _local_prompt_nodes.NODE_CLASS_MAPPINGS
LOCAL_PROMPT_NODE_DISPLAY_NAME_MAPPINGS = _local_prompt_nodes.NODE_DISPLAY_NAME_MAPPINGS

NODE_CLASS_MAPPINGS = {
    **PROMPT_NODE_CLASS_MAPPINGS,
    **LOCAL_PROMPT_NODE_CLASS_MAPPINGS,
    **IMAGE_NODE_CLASS_MAPPINGS,
    **LORA_NODE_CLASS_MAPPINGS,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    **PROMPT_NODE_DISPLAY_NAME_MAPPINGS,
    **LOCAL_PROMPT_NODE_DISPLAY_NAME_MAPPINGS,
    **IMAGE_NODE_DISPLAY_NAME_MAPPINGS,
    **LORA_NODE_DISPLAY_NAME_MAPPINGS,
}

WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
