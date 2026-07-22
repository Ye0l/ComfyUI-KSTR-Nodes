from math import sqrt
from typing import Any

import torch


TOKEN_NORMALIZATIONS = ("none", "mean", "length", "length+mean")
WEIGHT_INTERPRETATIONS = ("comfy", "A1111", "compel", "comfy++", "down_weight")


def _replace_weight(token_item: Any, new_weight: float):
    if isinstance(token_item, tuple):
        return (token_item[0], float(new_weight), *token_item[2:])
    if isinstance(token_item, list):
        updated = list(token_item)
        if len(updated) >= 2:
            updated[1] = float(new_weight)
        return updated
    return token_item


def _token_references(token_stream):
    references = []
    for chunk_index, chunk in enumerate(token_stream):
        for token_index, token_item in enumerate(chunk):
            if not isinstance(token_item, (tuple, list)) or len(token_item) < 3:
                continue
            word_id = token_item[2]
            if word_id in (None, 0):
                continue
            try:
                weight = float(token_item[1])
            except (TypeError, ValueError):
                continue
            references.append((chunk_index, token_index, word_id, weight))
    return references


def _normalize_token_stream(token_stream, mode: str):
    chunks = [list(chunk) for chunk in token_stream]
    if mode == "none":
        return chunks

    references = _token_references(chunks)
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
        shift = 1.0 - mean_weight
        weights = [weight + shift for weight in weights]

    for (chunk_index, token_index, _, _), weight in zip(references, weights):
        chunks[chunk_index][token_index] = _replace_weight(
            chunks[chunk_index][token_index], weight
        )

    return chunks


def normalize_token_weights(tokenized: dict, mode: str) -> dict:
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


def _map_stream_weights(token_stream, mapper):
    chunks = [list(chunk) for chunk in token_stream]
    references = _token_references(chunks)
    if not references:
        return chunks

    weights = [reference[3] for reference in references]
    mapped = mapper(weights)

    for (chunk_index, token_index, _, _), weight in zip(references, mapped):
        chunks[chunk_index][token_index] = _replace_weight(
            chunks[chunk_index][token_index], weight
        )
    return chunks


def _mean_scale(weights):
    mean = sum(weights) / len(weights)
    if abs(mean) < 1e-8:
        return weights
    return [weight / mean for weight in weights]


def _scale_max_to_one(weights):
    maximum = max(weights)
    if maximum <= 1.0 or abs(maximum) < 1e-8:
        return weights
    return [weight / maximum for weight in weights]


def _apply_anima_interpretation(tokenized: dict, interpretation: str) -> dict:
    """Apply an Anima-safe weighting fallback to its T5 control stream.

    ComfyUI's Anima encoder intentionally forces Qwen token weights to 1.0 and
    forwards T5 token weights as conditioning metadata. Rewriting the T5 stream
    therefore preserves Anima's native qwen3_06b/t5xxl pipeline and avoids the
    SD1/SDXL-only `l` key assumption.
    """
    output = {key: [list(chunk) for chunk in value] for key, value in tokenized.items()}
    t5_key = "t5xxl" if "t5xxl" in output else None
    if t5_key is None:
        return output

    if interpretation == "A1111":
        output[t5_key] = _map_stream_weights(output[t5_key], _mean_scale)
    elif interpretation == "down_weight":
        output[t5_key] = _map_stream_weights(output[t5_key], _scale_max_to_one)
    elif interpretation in ("compel", "comfy++"):
        # Anima applies T5 weights after its LLM adapter. Keeping the normalized
        # token weights is the model-safe equivalent when no CLIP embedding
        # stream exists to run mask-based CLIP algorithms against.
        pass
    elif interpretation != "comfy":
        raise ValueError(f"Unsupported weight interpretation: {interpretation!r}")

    return output


def _is_anima_tokens(tokenized: dict) -> bool:
    return "qwen3_06b" in tokenized and "t5xxl" in tokenized


def _pick_embedding_stream(tokenized: dict) -> str:
    if "l" in tokenized:
        return "l"
    if len(tokenized) == 1:
        return next(iter(tokenized))
    for key in tokenized:
        if key not in {"g", "t5xxl"}:
            return key
    return next(iter(tokenized))


def _stream_components(token_stream):
    tokens = [[item[0] for item in chunk] for chunk in token_stream]
    weights = [[float(item[1]) for item in chunk] for chunk in token_stream]
    word_ids = [[item[2] for item in chunk] for chunk in token_stream]
    return tokens, weights, word_ids


def _tokens_with_weights(tokens, weights):
    return [
        [(token, weight) for token, weight in zip(token_row, weight_row)]
        for token_row, weight_row in zip(tokens, weights)
    ]


def _tokens_unweighted(tokens):
    return [[(token, 1.0) for token in row] for row in tokens]


def _encode_replaced_stream(clip, tokenized, stream_key, stream):
    replaced = {key: value for key, value in tokenized.items()}
    replaced[stream_key] = stream
    result = clip.encode_from_tokens(replaced, return_pooled=True, return_dict=True)
    return result["cond"], result


def _a1111_embedding(clip, tokenized, stream_key):
    tokens, weights, _ = _stream_components(tokenized[stream_key])
    base, base_info = _encode_replaced_stream(
        clip, tokenized, stream_key, _tokens_unweighted(tokens)
    )
    weight_tensor = torch.tensor(weights, dtype=base.dtype, device=base.device)
    weight_tensor = weight_tensor.reshape(1, -1, 1)
    if weight_tensor.shape[1] != base.shape[1]:
        raise RuntimeError(
            "A1111 weighting requires the selected token stream length to match "
            "the conditioning sequence length."
        )
    weighted = base * weight_tensor
    weighted_mean = weighted.mean()
    if torch.abs(weighted_mean) > 1e-8:
        weighted = weighted * (base.mean() / weighted_mean)
    return weighted, base_info


def _native_embedding_fallback(clip, tokenized, stream_key, interpretation):
    tokens, weights, _ = _stream_components(tokenized[stream_key])

    if interpretation == "down_weight":
        flat = [weight for row in weights for weight in row]
        maximum = max(flat) if flat else 1.0
        if maximum > 1.0:
            weights = [[weight / maximum for weight in row] for row in weights]
    elif interpretation == "compel":
        # Preserve positive weights and let ComfyUI's native encoder process
        # negative weights. This keeps the mode usable on modern encoders that
        # do not expose SD1-style mask tokens.
        weights = [[weight if weight >= 1.0 else weight for weight in row] for row in weights]
    elif interpretation == "comfy++":
        # Native Comfy weighting is the safest generalized fallback for encoders
        # without a stable, model-specific masking token.
        pass
    else:
        raise ValueError(f"Unsupported weight interpretation: {interpretation!r}")

    return _encode_replaced_stream(
        clip, tokenized, stream_key, _tokens_with_weights(tokens, weights)
    )


def _conditioning_from_info(cond, info):
    metadata = {
        key: value
        for key, value in info.items()
        if key not in {"cond", "pooled_output"}
    }
    metadata["pooled_output"] = info.get("pooled_output")
    return [[cond, metadata]]


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
                    {"default": "comfy"},
                ),
            }
        }

    RETURN_TYPES = ("CONDITIONING",)
    RETURN_NAMES = ("conditioning",)
    FUNCTION = "encode"
    CATEGORY = "Yeol/Conditioning"
    DESCRIPTION = (
        "Advanced text encoder with none/mean/length/length+mean token "
        "normalization and comfy/A1111/compel/comfy++/down_weight modes. "
        "Anima qwen3_06b/t5xxl metadata is preserved."
    )

    def encode(self, text, clip, token_normalization, weight_interpretation):
        if clip is None:
            raise RuntimeError(
                "CLIP input is invalid: None. Connect a valid CLIP/text encoder."
            )
        if weight_interpretation not in WEIGHT_INTERPRETATIONS:
            raise ValueError(
                f"Unsupported weight interpretation: {weight_interpretation!r}"
            )

        tokenized = clip.tokenize(text, return_word_ids=True)
        normalized = normalize_token_weights(tokenized, token_normalization)

        if _is_anima_tokens(normalized):
            interpreted = _apply_anima_interpretation(
                normalized, weight_interpretation
            )
            return (clip.encode_from_tokens_scheduled(interpreted),)

        if weight_interpretation == "comfy":
            return (clip.encode_from_tokens_scheduled(normalized),)

        stream_key = _pick_embedding_stream(normalized)
        if weight_interpretation == "A1111":
            cond, info = _a1111_embedding(clip, normalized, stream_key)
        else:
            cond, info = _native_embedding_fallback(
                clip, normalized, stream_key, weight_interpretation
            )
        return (_conditioning_from_info(cond, info),)


NODE_CLASS_MAPPINGS = {
    "YeolCLIPTextEncodeAdvanced": CLIPTextEncodeAdvanced,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "YeolCLIPTextEncodeAdvanced": "CLIP Text Encode (Advanced, KSTR)",
}
