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


def _mask_indices(tokens, indices, mask_token):
    row_length = len(tokens[0])
    selected = set(indices)
    return [
        [
            mask_token if row_index * row_length + token_index in selected else token
            for token_index, token in enumerate(row)
        ]
        for row_index, row in enumerate(tokens)
    ]


def _batched_encode_stream(clip, tokenized, stream_key, streams, section_count):
    outputs = []
    for offset in range(0, len(streams), 32):
        batch = streams[offset : offset + 32]
        repeated = {key: value for key, value in tokenized.items()}
        repeated[stream_key] = batch
        multiplier = max(1, len(batch) // section_count)
        for key, value in list(repeated.items()):
            if key != stream_key:
                repeated[key] = list(value) * multiplier
        info = clip.encode_from_tokens(repeated, return_pooled=True, return_dict=True)
        outputs.append(info["cond"].reshape(len(batch), len(batch[0]), -1))
    return torch.cat(outputs, dim=0)


def _down_weight_embedding(
    clip,
    tokenized,
    stream_key,
    tokens,
    weights,
    base,
    mask_token=(266, 1.0),
):
    flat_weights = [weight for row in weights for weight in row]
    unique_weights = sorted(set(flat_weights))
    if not any(weight < 1.0 for weight in unique_weights):
        return base

    inverse = [unique_weights.index(weight) for weight in flat_weights]
    masked_current = _tokens_unweighted(tokens)
    masked_streams = []

    for weight_index, weight in enumerate(unique_weights):
        if weight >= 1.0:
            continue
        indices = [
            index for index, inverse_index in enumerate(inverse)
            if inverse_index == weight_index
        ]
        masked_current = _mask_indices(masked_current, indices, mask_token)
        masked_streams.extend(masked_current)

    encoded = _batched_encode_stream(
        clip,
        tokenized,
        stream_key,
        masked_streams,
        len(tokens),
    )
    encoded = torch.cat([base, encoded], dim=0)
    reduced = [weight for weight in unique_weights if weight <= 1.0]
    mix = [reduced[0]] + [right - left for left, right in zip(reduced, reduced[1:])]
    mix_tensor = torch.tensor(mix, dtype=encoded.dtype, device=encoded.device).reshape(-1, 1, 1)
    return (mix_tensor * encoded).sum(dim=0, keepdim=True)


def _up_weight_embedding(
    clip,
    tokenized,
    stream_key,
    tokens,
    weights,
    word_ids,
    base,
    mask_token=(266, 1.0),
):
    changed = {}
    for word_row, weight_row in zip(word_ids, weights):
        for word_id, weight in zip(word_row, weight_row):
            if word_id in (None, 0) or weight <= 1.0 or word_id in changed:
                continue
            changed[word_id] = weight

    if not changed:
        return torch.zeros_like(base)

    masked_streams = []
    masks = []
    for word_id in changed:
        masked = []
        mask = []
        for token_row, word_row in zip(tokens, word_ids):
            masked.append([
                mask_token if current_word_id == word_id else (token, 1.0)
                for token, current_word_id in zip(token_row, word_row)
            ])
            mask.extend(current_word_id == word_id for current_word_id in word_row)
        masked_streams.extend(masked)
        masks.append(mask)

    encoded = _batched_encode_stream(
        clip,
        tokenized,
        stream_key,
        masked_streams,
        len(tokens),
    )
    differences = base.expand(encoded.shape) - encoded

    result = torch.zeros_like(base)
    for index, (word_id, weight) in enumerate(changed.items()):
        mask_tensor = torch.tensor(
            masks[index], dtype=base.dtype, device=base.device
        ).reshape(1, -1, 1)
        result += differences[index : index + 1] * mask_tensor * (weight - 1.0)
    return result


def _advanced_embedding(clip, tokenized, stream_key, interpretation):
    tokens, weights, word_ids = _stream_components(tokenized[stream_key])
    unweighted = _tokens_unweighted(tokens)
    base, base_info = _encode_replaced_stream(
        clip, tokenized, stream_key, unweighted
    )

    if interpretation == "compel":
        positive_weights = [
            [weight if weight >= 1.0 else 1.0 for weight in row]
            for row in weights
        ]
        positive, info = _encode_replaced_stream(
            clip,
            tokenized,
            stream_key,
            _tokens_with_weights(tokens, positive_weights),
        )
        return _down_weight_embedding(
            clip, tokenized, stream_key, tokens, weights, positive
        ), info

    if interpretation == "comfy++":
        down = _down_weight_embedding(
            clip, tokenized, stream_key, tokens, weights, base
        )
        up = _up_weight_embedding(
            clip, tokenized, stream_key, tokens, weights, word_ids, base
        )
        return down + up, base_info

    if interpretation == "down_weight":
        flat = [weight for row in weights for weight in row]
        maximum = max(flat) if flat else 1.0
        scaled = (
            [[weight / maximum for weight in row] for row in weights]
            if maximum > 1.0
            else weights
        )
        return _down_weight_embedding(
            clip, tokenized, stream_key, tokens, scaled, base
        ), base_info

    raise ValueError(f"Unsupported weight interpretation: {interpretation!r}")

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
            cond, info = _advanced_embedding(
                clip, normalized, stream_key, weight_interpretation
            )
        return (_conditioning_from_info(cond, info),)


NODE_CLASS_MAPPINGS = {
    "YeolCLIPTextEncodeAdvanced": CLIPTextEncodeAdvanced,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "YeolCLIPTextEncodeAdvanced": "CLIP Text Encode (Advanced, KSTR)",
}
