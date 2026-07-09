import logging
from concurrent.futures import ThreadPoolExecutor

from .image_nodes import (
    ImageToWebP,
    PostWebPApi as SyncPostWebPApi,
    SendTelegramWebP as SyncSendTelegramWebP,
)


logger = logging.getLogger(__name__)
UPLOAD_EXECUTOR = ThreadPoolExecutor(
    max_workers=4,
    thread_name_prefix="kstr-upload",
)


def run_background(label, function, *args, **kwargs):
    try:
        function(*args, **kwargs)
        logger.info("%s completed", label)
    except Exception:
        logger.exception("%s failed", label)


class SendTelegramWebP(SyncSendTelegramWebP):
    @classmethod
    def INPUT_TYPES(cls):
        input_types = super().INPUT_TYPES()
        input_types["required"]["background_upload"] = (
            "BOOLEAN",
            {"default": True},
        )
        return input_types

    def send(
        self,
        webp,
        bot_token: str,
        chat_id: str,
        caption: str,
        send_as_document: bool,
        timeout_seconds: int,
        background_upload: bool,
    ):
        if not background_upload:
            return super().send(
                webp,
                bot_token,
                chat_id,
                caption,
                send_as_document,
                timeout_seconds,
            )

        UPLOAD_EXECUTOR.submit(
            run_background,
            "Telegram WEBP upload",
            super().send,
            webp,
            bot_token,
            chat_id,
            caption,
            send_as_document,
            timeout_seconds,
        )
        return (webp, "Telegram upload queued in background")


class PostWebPApi(SyncPostWebPApi):
    @classmethod
    def INPUT_TYPES(cls):
        input_types = super().INPUT_TYPES()
        input_types["required"]["background_upload"] = (
            "BOOLEAN",
            {"default": True},
        )
        return input_types

    def post(
        self,
        webp,
        api_url: str,
        api_key: str,
        device_id: str,
        filename_prefix_override: str,
        is_favorite: bool,
        timeout_seconds: int,
        background_upload: bool,
    ):
        if not background_upload:
            return super().post(
                webp,
                api_url,
                api_key,
                device_id,
                filename_prefix_override,
                is_favorite,
                timeout_seconds,
            )

        UPLOAD_EXECUTOR.submit(
            run_background,
            "Immich WEBP upload",
            super().post,
            webp,
            api_url,
            api_key,
            device_id,
            filename_prefix_override,
            is_favorite,
            timeout_seconds,
        )
        return (webp, "Immich upload queued in background")


NODE_CLASS_MAPPINGS = {
    "YeolImageToWebP": ImageToWebP,
    "YeolSendTelegramWebP": SendTelegramWebP,
    "YeolPostWebPApi": PostWebPApi,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "YeolImageToWebP": "Image to WEBP",
    "YeolSendTelegramWebP": "Send WEBP to Telegram",
    "YeolPostWebPApi": "POST WEBP to Immich",
}
