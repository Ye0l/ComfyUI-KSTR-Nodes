\
import io
import json
from xml.sax.saxutils import escape

import numpy as np
import requests
from PIL import Image


def tensor_to_pil(image_tensor) -> Image.Image:
    array = image_tensor.detach().cpu().numpy()
    array = np.clip(array * 255.0, 0, 255).astype(np.uint8)

    if array.ndim != 3:
        raise ValueError(f"Expected HWC image tensor, got {array.shape}")

    channels = array.shape[2]

    if channels == 1:
        return Image.fromarray(array[:, :, 0], mode="L")
    if channels == 3:
        return Image.fromarray(array, mode="RGB")
    if channels == 4:
        return Image.fromarray(array, mode="RGBA")

    raise ValueError(f"Unsupported channel count: {channels}")


def parse_json_object(raw: str, name: str) -> dict:
    raw = raw.strip()
    if not raw:
        return {}

    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")

    return value


def build_xmp_packet(metadata: dict) -> bytes:
    json_text = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
    escaped_json = escape(json_text)

    xmp = f"""<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
    <rdf:Description xmlns:comfy="https://yeol.dev/ns/comfyui/1.0/">
      <comfy:metadata>{escaped_json}</comfy:metadata>
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""
    return xmp.encode("utf-8")


def encode_webp(
    image_tensor,
    quality: int,
    method: int,
    lossless: bool,
    metadata: dict | None,
) -> bytes:
    image = tensor_to_pil(image_tensor)
    buffer = io.BytesIO()

    save_kwargs = {
        "format": "WEBP",
        "quality": quality,
        "lossless": lossless,
        "method": method,
    }

    if metadata:
        save_kwargs["xmp"] = build_xmp_packet(metadata)

    image.save(buffer, **save_kwargs)
    return buffer.getvalue()


def make_webp_item(
    image_bytes: bytes,
    metadata: dict,
    index: int,
    filename_prefix: str = "comfyui",
):
    return {
        "bytes": image_bytes,
        "mime_type": "image/webp",
        "extension": "webp",
        "filename": f"{filename_prefix}_{index + 1}.webp",
        "metadata": metadata,
    }


def get_webp_bytes(item):
    if isinstance(item, dict):
        image_bytes = item.get("bytes")
        if not isinstance(image_bytes, (bytes, bytearray)):
            raise ValueError("WEBP item dict must contain bytes under 'bytes'")
        return bytes(image_bytes), item

    if isinstance(item, (bytes, bytearray)):
        return bytes(item), {
            "mime_type": "image/webp",
            "extension": "webp",
            "filename": "comfyui.webp",
            "metadata": {},
        }

    raise ValueError("WEBP item must be bytes or a dict containing bytes")


def build_metadata(
    embed_metadata: bool,
    metadata_json: str,
    include_prompt: bool,
    include_workflow: bool,
    prompt,
    extra_pnginfo,
):
    if not embed_metadata:
        return {}

    metadata = {}
    custom_metadata = parse_json_object(metadata_json, "metadata_json")

    if include_prompt and prompt is not None:
        metadata["prompt"] = prompt

    if include_workflow and extra_pnginfo is not None:
        metadata["extra_pnginfo"] = extra_pnginfo

    if custom_metadata:
        metadata["custom"] = custom_metadata

    return metadata


class ImageToWebP:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "quality": (
                    "INT",
                    {
                        "default": 95,
                        "min": 1,
                        "max": 100,
                        "step": 1,
                    },
                ),
                "method": (
                    "INT",
                    {
                        "default": 6,
                        "min": 0,
                        "max": 6,
                        "step": 1,
                    },
                ),
                "lossless": ("BOOLEAN", {"default": False}),
                "embed_metadata": ("BOOLEAN", {"default": True}),
                "include_prompt_metadata": ("BOOLEAN", {"default": True}),
                "include_workflow_metadata": ("BOOLEAN", {"default": True}),
                "metadata_json": (
                    "STRING",
                    {
                        "default": "{}",
                        "multiline": True,
                    },
                ),
                "filename_prefix": (
                    "STRING",
                    {
                        "default": "comfyui",
                        "multiline": False,
                    },
                ),
            },
            "hidden": {
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
            },
        }

    RETURN_TYPES = ("WEBP",)
    RETURN_NAMES = ("webp",)
    FUNCTION = "convert"
    CATEGORY = "Yeol/Image"

    def convert(
        self,
        image,
        quality: int,
        method: int,
        lossless: bool,
        embed_metadata: bool,
        include_prompt_metadata: bool,
        include_workflow_metadata: bool,
        metadata_json: str,
        filename_prefix: str,
        prompt=None,
        extra_pnginfo=None,
    ):
        filename_prefix = filename_prefix.strip() or "comfyui"

        metadata = build_metadata(
            embed_metadata=embed_metadata,
            metadata_json=metadata_json,
            include_prompt=include_prompt_metadata,
            include_workflow=include_workflow_metadata,
            prompt=prompt,
            extra_pnginfo=extra_pnginfo,
        )

        webp_batch = []
        for index, image_tensor in enumerate(image):
            image_bytes = encode_webp(
                image_tensor=image_tensor,
                quality=quality,
                method=method,
                lossless=lossless,
                metadata=metadata,
            )
            webp_batch.append(
                make_webp_item(
                    image_bytes=image_bytes,
                    metadata=metadata,
                    index=index,
                    filename_prefix=filename_prefix,
                )
            )

        return (webp_batch,)


class SendTelegramWebP:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "webp": ("WEBP",),
                "bot_token": ("STRING", {"default": ""}),
                "chat_id": ("STRING", {"default": ""}),
                "caption": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                    },
                ),
                "send_as_document": ("BOOLEAN", {"default": True}),
                "timeout_seconds": (
                    "INT",
                    {
                        "default": 60,
                        "min": 1,
                        "max": 600,
                    },
                ),
            }
        }

    RETURN_TYPES = ("WEBP", "STRING")
    RETURN_NAMES = ("webp", "response")
    FUNCTION = "send"
    CATEGORY = "Yeol/Network"
    OUTPUT_NODE = True

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def send(
        self,
        webp,
        bot_token: str,
        chat_id: str,
        caption: str,
        send_as_document: bool,
        timeout_seconds: int,
    ):
        bot_token = bot_token.strip()
        chat_id = chat_id.strip()

        if not bot_token:
            raise ValueError("bot_token is empty")
        if not chat_id:
            raise ValueError("chat_id is empty")

        if send_as_document:
            url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
            file_field = "document"
        else:
            url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
            file_field = "photo"

        responses = []

        for index, item in enumerate(webp):
            image_bytes, info = get_webp_bytes(item)
            filename = info.get("filename") or f"comfyui_{index + 1}.webp"

            response = requests.post(
                url,
                data={
                    "chat_id": chat_id,
                    "caption": caption,
                },
                files={
                    file_field: (
                        filename,
                        image_bytes,
                        "image/webp",
                    )
                },
                timeout=timeout_seconds,
            )

            body = response.text
            if not response.ok:
                raise RuntimeError(
                    f"Telegram request failed ({response.status_code}): {body}"
                )

            responses.append(body)

        return (webp, "\n".join(responses))


class PostWebPApi:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "webp": ("WEBP",),
                "url": (
                    "STRING",
                    {
                        "default": "https://example.com/upload",
                    },
                ),
                "image_field_name": (
                    "STRING",
                    {
                        "default": "image",
                    },
                ),
                "filename_prefix_override": (
                    "STRING",
                    {
                        "default": "",
                    },
                ),
                "headers_json": (
                    "STRING",
                    {
                        "default": "{}",
                        "multiline": True,
                    },
                ),
                "form_fields_json": (
                    "STRING",
                    {
                        "default": "{}",
                        "multiline": True,
                    },
                ),
                "timeout_seconds": (
                    "INT",
                    {
                        "default": 60,
                        "min": 1,
                        "max": 600,
                    },
                ),
            }
        }

    RETURN_TYPES = ("WEBP", "STRING")
    RETURN_NAMES = ("webp", "response")
    FUNCTION = "post"
    CATEGORY = "Yeol/Network"
    OUTPUT_NODE = True

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def post(
        self,
        webp,
        url: str,
        image_field_name: str,
        filename_prefix_override: str,
        headers_json: str,
        form_fields_json: str,
        timeout_seconds: int,
    ):
        url = url.strip()
        image_field_name = image_field_name.strip()
        filename_prefix_override = filename_prefix_override.strip()

        if not url:
            raise ValueError("url is empty")
        if not image_field_name:
            raise ValueError("image_field_name is empty")

        headers = {
            str(key): str(value)
            for key, value in parse_json_object(
                headers_json,
                "headers_json",
            ).items()
        }
        form_fields = {
            str(key): str(value)
            for key, value in parse_json_object(
                form_fields_json,
                "form_fields_json",
            ).items()
        }

        responses = []

        for index, item in enumerate(webp):
            image_bytes, info = get_webp_bytes(item)
            filename = info.get("filename") or f"comfyui_{index + 1}.webp"

            if filename_prefix_override:
                filename = f"{filename_prefix_override}_{index + 1}.webp"

            response = requests.post(
                url,
                headers=headers,
                data=form_fields,
                files={
                    image_field_name: (
                        filename,
                        image_bytes,
                        "image/webp",
                    )
                },
                timeout=timeout_seconds,
            )

            body = response.text
            if not response.ok:
                raise RuntimeError(
                    f"POST request failed ({response.status_code}): {body}"
                )

            responses.append(body)

        return (webp, "\n".join(responses))


NODE_CLASS_MAPPINGS = {
    "YeolImageToWebP": ImageToWebP,
    "YeolSendTelegramWebP": SendTelegramWebP,
    "YeolPostWebPApi": PostWebPApi,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "YeolImageToWebP": "Image to WEBP",
    "YeolSendTelegramWebP": "Send WEBP to Telegram",
    "YeolPostWebPApi": "POST WEBP API",
}
