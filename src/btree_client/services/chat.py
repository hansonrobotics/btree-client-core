import json
import logging
import os

import aiohttp
import requests

from btree_client.utils import get_language_code

logger = logging.getLogger(__name__)


class ChatClient(object):
    def __init__(self):
        self.url = os.environ.get("CHAT_BASE_URL", "http://localhost:9100")

    def chat(self, uid, text, lang, **kwargs):
        lang = get_language_code(lang)
        payload = json.dumps({"uid": uid, "question": text, "lang": lang})
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if "CHAT_TOKEN" in os.environ:
            headers["Authorization"] = "Bearer %s" % os.environ.get("CHAT_TOKEN")
        try:
            resp = requests.post(f"{self.url}/chat", headers=headers, data=payload)
            if resp.ok:
                response = resp.json()
                return response
            else:
                logger.error("Error %s(%r)", resp.status_code, resp.reason)
        except Exception as ex:
            logger.error("Chat client error %s", ex)

    async def async_chat(self, uid, text, lang, **kwargs):
        lang = get_language_code(lang)
        payload = json.dumps({"uid": uid, "question": text, "lang": lang})
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if "CHAT_TOKEN" in os.environ:
            headers["Authorization"] = "Bearer %s" % os.environ.get("CHAT_TOKEN")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.url, headers=headers, data=payload
                ) as resp:
                    if resp.ok:
                        response = await resp.json()
                        return response
                    else:
                        logger.error("Error %s(%r)", resp.status, resp.reason)
        except Exception as ex:
            logger.exception("Chat client error %s", ex)


if __name__ == "__main__":
    import asyncio

    asyncio.run(ChatClient().async_chat("default", "hello", "en-US"))
