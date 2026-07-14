import gc
import json
import os
import re
from typing import Dict, Tuple


DEFAULT_MODEL = "LGAI-EXAONE/EXAONE-3.5-2.4B-Instruct"
MODEL_ENV_NAME = "KSTR_PROMPT_MODEL"


_FORMAT_INSTRUCTIONS = {
    "anime_tags": (
        "Write the positive prompt as concise English comma-separated image tags. "
        "Prefer concrete subjects, appearance, action, setting, composition, lighting, and mood. "
        "Do not write explanatory sentences."
    ),
    "natural_language": (
        "Write the positive prompt as polished English natural-language prose suitable for "
        "a modern text-to-image model such as FLUX or SD3. Keep it visually concrete and concise."
    ),
    "hybrid": (
        "Write the positive prompt as one concise English scene description followed by "
        "comma-separated visual modifiers for composition, lighting, color, and mood."
    ),
}

_CREATIVITY_INSTRUCTIONS = {
    "strict": (
        "Do not invent unspecified character traits, colors, clothing, objects, or identities. "
        "Only reorganize and clarify details explicitly present in the user's description."
    ),
    "balanced": (
        "Preserve every explicit detail. You may add restrained composition, camera, lighting, "
        "and atmosphere cues when they are directly compatible with the description."
    ),
    "creative": (
        "Preserve every explicit detail. You may add supporting visual details, composition, "
        "lighting, and atmosphere, but never contradict the description."
    ),
}

_LITERAL_PATTERN = re.compile(
    r"(<lora:[^>\n]+>|<[^>\n]+>|__[^_\n]+__|\{[^{}\n]+\}|"
    r"\([^()\n]+:[+-]?(?:\d+(?:\.\d*)?|\.\d+)\)|\[[^\[\]\n]+\])"
)


class KoreanImagePrompt:
    _model = None
    _tokenizer = None
    _model_source = None
    _device = None

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "description": (
                    "STRING",
                    {
                        "multiline": True,
                        "dynamicPrompts": True,
                        "default": "",
                    },
                ),
                "prompt_format": (
                    ["anime_tags", "natural_language", "hybrid"],
                    {"default": "anime_tags"},
                ),
                "creativity": (
                    ["strict", "balanced", "creative"],
                    {"default": "balanced"},
                ),
                "seed": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 0xFFFFFFFFFFFFFFFF,
                    },
                ),
                "max_new_tokens": (
                    "INT",
                    {
                        "default": 256,
                        "min": 64,
                        "max": 1024,
                        "step": 16,
                    },
                ),
                "keep_model_loaded": (
                    "BOOLEAN",
                    {"default": False},
                ),
            },
            "optional": {
                "style_prefix": (
                    "STRING",
                    {
                        "multiline": True,
                        "dynamicPrompts": True,
                        "default": "",
                    },
                ),
                "negative_hint": (
                    "STRING",
                    {
                        "multiline": True,
                        "dynamicPrompts": True,
                        "default": "",
                    },
                ),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("positive_prompt", "negative_prompt")
    FUNCTION = "compose"
    CATEGORY = "Yeol/Prompt"

    @classmethod
    def _resolve_model_source(cls) -> str:
        return os.environ.get(MODEL_ENV_NAME, DEFAULT_MODEL).strip() or DEFAULT_MODEL

    @classmethod
    def _load_model(cls):
        model_source = cls._resolve_model_source()
        if cls._model is not None and cls._model_source == model_source:
            return cls._model, cls._tokenizer, cls._device

        cls.unload_model()

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError(
                "Korean Image Prompt requires transformers>=4.43. "
                "Install it in the ComfyUI Python environment with: "
                "pip install -r custom_nodes/ComfyUI-KSTR-Nodes/requirements-llm.txt"
            ) from exc

        if torch.cuda.is_available():
            device = torch.device("cuda")
            dtype = (
                torch.bfloat16
                if getattr(torch.cuda, "is_bf16_supported", lambda: False)()
                else torch.float16
            )
        else:
            device = torch.device("cpu")
            dtype = torch.float32

        try:
            tokenizer = AutoTokenizer.from_pretrained(
                model_source,
                trust_remote_code=True,
            )
            model = AutoModelForCausalLM.from_pretrained(
                model_source,
                trust_remote_code=True,
                torch_dtype=dtype,
            )
            model.to(device)
            model.eval()
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load prompt model from {model_source!r}. "
                f"Set {MODEL_ENV_NAME} to a valid local model directory or Hugging Face model ID."
            ) from exc

        cls._model = model
        cls._tokenizer = tokenizer
        cls._model_source = model_source
        cls._device = device
        return model, tokenizer, device

    @classmethod
    def unload_model(cls):
        cls._model = None
        cls._tokenizer = None
        cls._model_source = None
        cls._device = None
        gc.collect()

        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

    @staticmethod
    def _protect_literals(text: str) -> Tuple[str, Dict[str, str]]:
        literals: Dict[str, str] = {}

        def replace(match: re.Match) -> str:
            key = f"KSTR_LITERAL_{len(literals):03d}"
            literals[key] = match.group(0)
            return key

        return _LITERAL_PATTERN.sub(replace, text), literals

    @staticmethod
    def _restore_literals(text: str, literals: Dict[str, str]) -> str:
        restored = text
        for key, value in literals.items():
            restored = restored.replace(key, value)
        return restored

    @staticmethod
    def _build_messages(
        description: str,
        prompt_format: str,
        creativity: str,
        style_prefix: str,
        negative_hint: str,
    ):
        system_prompt = f"""You are an image-generation prompt composer specialized in Korean input.
Convert the user's Korean natural-language scene description into an effective English image prompt.

Rules:
- Preserve all explicit facts and relationships in the source.
- Never add artist names, copyrighted work names, quality spam, or model-specific trigger words unless the user supplied them.
- Preserve every KSTR_LITERAL_NNN token exactly as written.
- Produce a useful negative prompt, but do not negate anything explicitly requested by the user.
- Return only one valid JSON object. Do not use Markdown or commentary.
- The JSON schema is exactly: {{"positive_prompt":"...","negative_prompt":"..."}}

Output format:
{_FORMAT_INSTRUCTIONS[prompt_format]}

Creativity policy:
{_CREATIVITY_INSTRUCTIONS[creativity]}
"""

        user_parts = [f"Scene description:\n{description.strip()}"]
        if style_prefix.strip():
            user_parts.append(
                "Required style or prefix instructions:\n" + style_prefix.strip()
            )
        if negative_hint.strip():
            user_parts.append(
                "Negative prompt hints supplied by the user:\n" + negative_hint.strip()
            )

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "\n\n".join(user_parts)},
        ]

    @staticmethod
    def _parse_response(text: str) -> Tuple[str, str]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, count=1)
            cleaned = re.sub(r"\s*```$", "", cleaned, count=1)

        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(cleaned[start : end + 1])
                positive = str(parsed.get("positive_prompt", "")).strip()
                negative = str(parsed.get("negative_prompt", "")).strip()
                if positive:
                    return positive, negative
            except (TypeError, ValueError, json.JSONDecodeError):
                pass

        positive_match = re.search(
            r"positive(?:_prompt)?\s*[:=]\s*(.+?)(?=\n\s*negative(?:_prompt)?\s*[:=]|$)",
            cleaned,
            flags=re.IGNORECASE | re.DOTALL,
        )
        negative_match = re.search(
            r"negative(?:_prompt)?\s*[:=]\s*(.+)$",
            cleaned,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if positive_match:
            positive = positive_match.group(1).strip().strip('"')
            negative = (
                negative_match.group(1).strip().strip('"') if negative_match else ""
            )
            return positive, negative

        return cleaned, ""

    def compose(
        self,
        description: str,
        prompt_format: str,
        creativity: str,
        seed: int,
        max_new_tokens: int,
        keep_model_loaded: bool,
        style_prefix: str = "",
        negative_hint: str = "",
    ):
        if not description.strip():
            return "", ""

        protected_description, literals = self._protect_literals(description)
        protected_style, style_literals = self._protect_literals(style_prefix)
        protected_negative, negative_literals = self._protect_literals(negative_hint)

        offset = len(literals)
        remapped_style = {
            f"KSTR_LITERAL_{index + offset:03d}": value
            for index, value in enumerate(style_literals.values())
        }
        for old_key, new_key in zip(style_literals, remapped_style):
            protected_style = protected_style.replace(old_key, new_key)
        literals.update(remapped_style)

        offset = len(literals)
        remapped_negative = {
            f"KSTR_LITERAL_{index + offset:03d}": value
            for index, value in enumerate(negative_literals.values())
        }
        for old_key, new_key in zip(negative_literals, remapped_negative):
            protected_negative = protected_negative.replace(old_key, new_key)
        literals.update(remapped_negative)

        model, tokenizer, device = self._load_model()

        try:
            import torch

            messages = self._build_messages(
                protected_description,
                prompt_format,
                creativity,
                protected_style,
                protected_negative,
            )
            input_ids = tokenizer.apply_chat_template(
                messages,
                tokenize=True,
                add_generation_prompt=True,
                return_tensors="pt",
            ).to(device)

            do_sample = creativity != "strict"
            generation_kwargs = {
                "max_new_tokens": max_new_tokens,
                "do_sample": do_sample,
                "eos_token_id": tokenizer.eos_token_id,
                "pad_token_id": tokenizer.eos_token_id,
            }
            if do_sample:
                generation_kwargs.update(
                    {
                        "temperature": 0.35 if creativity == "balanced" else 0.7,
                        "top_p": 0.9,
                        "generator": torch.Generator(device=device).manual_seed(seed),
                    }
                )

            with torch.inference_mode():
                output_ids = model.generate(input_ids, **generation_kwargs)

            generated_ids = output_ids[0, input_ids.shape[-1] :]
            response = tokenizer.decode(generated_ids, skip_special_tokens=True)
            positive, negative = self._parse_response(response)
            positive = self._restore_literals(positive, literals)
            negative = self._restore_literals(negative, literals)
            return positive, negative
        finally:
            if not keep_model_loaded:
                self.unload_model()


NODE_CLASS_MAPPINGS = {
    "YeolKoreanImagePrompt": KoreanImagePrompt,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "YeolKoreanImagePrompt": "Korean Image Prompt (EXAONE)",
}
