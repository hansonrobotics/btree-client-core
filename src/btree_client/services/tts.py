import base64
import logging
import os

import aiohttp
import requests

logger = logging.getLogger(__name__)


class TTSResponse(object):
    def __init__(self):
        self.response = None
        self.params = {}

    def get_duration(self):
        if self.response:
            return self.response.get("duration", 0)
        return 0

    def write(self, wavfile):
        if self.response:
            data = self.response["data"]
            data = base64.b64decode(data)
            try:
                with open(wavfile, "wb") as f:
                    f.write(data)
                logger.debug("Write to file {}".format(wavfile))
                return True
            except Exception as ex:
                logger.error(ex)
                f = None
            finally:
                if f:
                    f.close()
        else:
            logger.error("No data to write")
        return False

    def __repr__(self):
        return "<TTSResponse params {}, duration {}>".format(
            self.params, self.get_duration()
        )


class TTSClient(object):
    def __init__(self, format):
        host = os.environ.get("TTS_HOST", "localhost")
        self.format = format
        self.tts3_url = f"http://{host}:10002/v1.0/tts"
        self.tts_url = f"http://{host}:10001/v1.0/tts"

    def get_url(self, vendor):
        return self.tts3_url if vendor != "cereproc" else self.tts_url

    async def async_tts(self, text, vendor, voice):
        params = {
            "text": text,
            "vendor": vendor,
            "voice": voice,
            "format": self.format,
        }
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        result = TTSResponse()
        url = self.get_url(vendor)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params) as resp:
                    response = await resp.json()
                    result.response = response.get("response")
                    result.params = params
        except Exception as ex:
            logger.error("TTS error %s", ex)

        return result

    def tts(self, text, vendor, voice):
        params = {
            "text": text,
            "vendor": vendor,
            "voice": voice,
            "format": self.format,
        }
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        result = TTSResponse()
        url = self.get_url(vendor)
        try:
            r = requests.get(url, headers=headers, params=params)
            response = r.json().get("response")
            result.response = response
            result.params = params
        except Exception as ex:
            logger.error("TTS error %s", ex)

        return result


if __name__ == "__main__":
    import asyncio

    asyncio.run(TTSClient("wav").async_tts("hello", "cereproc", "audrey"))
