from math import sqrt
from typing import Any


TOKEN_NORMALIZATIONS = ("none", "mean", "length", "length+mean")
WEIGHT_INTERPRETATIONS = ("comfy",)


def _replace_weight(token_item: Any, new_weight: float):
    """Return a token tuple/list with only its weight replaced."""
    if isinstance(token_item, tuple):
        return (token_item[0], float(new_weight), *token_item[2:])
    if isinstance(token_item, list):
        updated = list(token_item)
        updated[1] = float(new_weight)
        return updated
    return token_item


def _normalize_token_stream(token_stream, mode: str):
    """Normalize one ComfyUI tokenizer stream while preserving its shape."""
    chunks = [list(chunk) for chunk in token_stream]
    if mode == "none":
        return chunks

    references = []
    for chunk_index, chunk in enumerate(chunks):
        for token_index, token_item in enumerate(chunk):
            if not isinstance(token_item, (tuple, list)) or len(token_item) < 3:
                continue

            word_id = token_item[2]
            if word_id is None or word_id == 0:
                continue

            try:
                weight = float(token_item[1])
            except (TypeError, ValueError):
                continue

            references.append((chunk_index, token_index, word_id, weight))

    # Modern ComfyUI returns word IDs when return_word_ids=True. A custom
    # tokenizer that does not provide them is left untouched rather than
    # accidentally normalizing padding or special tokens.
    if not references:
        return chunks

    weights = [reference[3] for reference in references]

    if mode.startswith("length"):
        token_counts = {}
        for _, _, word_id, _ in references:
            token_counts[word_id] = token_counts.get(word_id, 0) + 1

        weights = [
            1.0 + (weight - 1.0) / sqrt(token_counts[word_id])
            for (_, _, word_id, _), weight in zip(references, weights)
        ]

    if mode.endswith("mean"):
        mean_weight = sum(weights) / len(weights)
        mean_shift = 1.0 - mean_weight
        weights = [weight + mean_shift for weight in weights]

    for (chunk_index, token_index, _, _), weight in zip(references, weights):
        original = chunks[chunk_index][token_index]
        chunks[chunk_index][token_index] = _replace_weight(original, weight)

    return chunks


def normalize_token_weights(tokenized: dict, mode: str) -> dict:
    """Apply ADV_CLIP_emb-style token normalization to every encoder stream."""
    if mode not in TOKEN_NORMALIZATIONS:
        raise ValueError(
            f"Unsupported token normalization: {mode!r}. "
            f"Expected one of: {', '.join(TOKEN_NORMALIZATIONS)}"
        )
    if not isinstance(tokenized, dict):
        raise TypeError(
            "The connected CLIP tokenizer did not return ComfyUI's token dictionary."
        )

    return {
        encoder_name: _normalize_token_stream(token_stream, mode)
        for encoder_name, token_stream in tokenized.items()
    }


class CLIPTextEncodeAdvanced:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": (
                    "STRING",
                    {
                        "multiline": True,
                        "dynamicPrompts": True,
                        "default": "",
                    },
                ),
                "clip": ("CLIP",),
                "token_normalization": (
                    list(TOKEN_NORMALIZATIONS),
                    {"default": "mean"},
                ),
                "weight_interpretation": (
                    list(WEIGHT_INTERPRETATIONS),
                    {
                        "default": "comfy",
                        "tooltip": (
                            "Uses the connected model's native ComfyUI encoder. "
                            "This preserves model-specific metadata such as "
                            "Anima t5xxl_ids and t5xxl_weights."
                        ),
                    },
                ),
            }
        }

    RETURN_TYPES = ("CONDITIONING",)
    RETURN_NAMES = ("conditioning",)
    FUNCTION = "encode"
    CATEGORY = "Yeol/Conditioning"
    DESCRIPTION = (
        "Model-agnostic advanced text encoder. It normalizes token weights "
        "without assuming SD1/SDXL token keys such as l or g, then delegates "
        "encoding to the connected CLIP/text encoder."
    )

    def encode(
        self,
        text: str,
        clip,
        token_normalization: str,
        weight_interpretation: str,
    ):
        if clip is None:
            raise RuntimeError(
                "CLIP input is invalid: None. Connect a valid CLIP/text encoder."
            )
        if weight_interpretation != "comfy":
            raise ValueError(
                "Only the native ComfyUI weight interpretation is supported."
            )

        tokenized = clip.tokenize(text, return_word_ids=True)
        normalized_tokens = normalize_token_weights(
            tokenized,
            token_normalization,
        )
        return (clip.encode_from_tokens_scheduled(normalized_tokens),)


NODE_CLASS_MAPPINGS = {
    "YeolCLIPTextEncodeAdvanced": CLIPTextEncodeAdvanced,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "YeolCLIPTextEncodeAdvanced": "CLIP Text Encode (Advanced, KSTR)",
}
