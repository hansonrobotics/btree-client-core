import asyncio
import logging
import os
import threading

import yaml
from pydub import AudioSegment

import btree_client
from btree_client import playback
from btree_client.client import BehaviorClient
from btree_client.google_asr import GoogleSpeechRecognizer
from btree_client.schemas import ActionResult
from btree_client.services.tts import TTSClient
from btree_client.utils import get_language_code
from btree_client.vosk_asr import VoskSpeechRecognizer

logger = logging.getLogger(__name__)

assets_dir = os.path.join(os.path.dirname(btree_client.__file__), "assets")
start_wav_seg = AudioSegment.from_wav(os.path.join(assets_dir, "beep-start.wav"))
error_wav_seg = AudioSegment.from_wav(os.path.join(assets_dir, "beep-error.wav"))
DATA_DIR = os.environ.get("DATA_DIR", ".")
AUDIO_FORMAT = os.environ.get("AUDIO_FORMAT", "wav")  # or mp3
STREAM_AUDIO = os.environ.get("STREAM_AUDIO", "0")  # 0: no stream, 1: stream


class Robot(object):
    def __init__(self):
        self.set_lang("en")
        self.robot_speaking = threading.Event()
        self.user_speaking = threading.Event()
        self.enable_sound_effect = os.environ.get("SOUND_EFFECT") == "1"
        self.speech_queue = asyncio.LifoQueue()
        self.asr_context = []
        vosk_asr_model_dir = os.environ.get("VOSK_ASR_MODEL_DIR")
        if not vosk_asr_model_dir:
            logger.warning("No VOSK ASR model dir is not specified")
        else:
            self.vosk_models = VoskSpeechRecognizer.load_models(vosk_asr_model_dir)

    def set_lang(self, lang):
        self.lang = lang

    def set_asr_context(self, context: list):
        self.asr_context = context

    def start_recognizer(self, lang, beepsound=False, standby=False):
        if self.enable_sound_effect and beepsound:
            playback.play(start_wav_seg)
        logger.warning("[Start Talking Now]")
        if standby and lang in self.vosk_models.keys():
            speech_recognizer = VoskSpeechRecognizer(self, self.vosk_models)
            logger.info("Running offline speech recognition")
        else:
            speech_recognizer = GoogleSpeechRecognizer(self, self.asr_context)
        speech_recognizer.stop.clear()
        threading.Thread(
            target=speech_recognizer.start, args=(lang,), daemon=True
        ).start()
        return speech_recognizer

    async def user_start_speaking(self):
        while True:
            if self.user_speaking.is_set():
                return
            else:
                await asyncio.sleep(0.1)

    def empty_speech_queue(self):
        for _ in range(self.speech_queue.qsize()):
            self.speech_queue.get_nowait()
            self.speech_queue.task_done()
        logger.info("Emptied speech queue")

    async def asr(self, speech_recognizer):
        """Blocks until it gets the ASR results or user stops speaking"""
        speech = None
        while True:
            try:
                # The speech can be from keyboard input
                speech = self.speech_queue.get_nowait()
                if speech is None:
                    speech_recognizer.stop.set()
                    logger.warning("[Ignore Speech]")
                break
            except asyncio.queues.QueueEmpty:
                if not self.user_speaking.is_set():
                    return
                await asyncio.sleep(0.1)
        return speech

    async def wait_for_speech(self, timeout, lang, beepsound=False, standby=False):
        """Waits for user's speech"""
        speech_recognizer = self.start_recognizer(lang, beepsound, standby)
        self.user_speaking.clear()
        try:
            logger.info("Wait for speech event %s", timeout)
            await asyncio.wait_for(self.user_start_speaking(), timeout=timeout)
            logger.info("Wait for speech")
            result = await asyncio.wait_for(self.asr(speech_recognizer), timeout=30)
            if result:
                self.speech_queue.put_nowait(None)  # poison
                logger.warning("[Speech End]")
                logger.warning("Speech %r", result["transcript"])
                return result
            else:
                logger.info("No speech result")
        except asyncio.TimeoutError:
            logger.error("[Speech Timeout]")
            speech_recognizer.stop.set()
            if self.enable_sound_effect and beepsound:
                playback.play(error_wav_seg)


class GenericRobot(Robot, BehaviorClient):
    def __init__(self, uid, conversation_id=None, namespace="/"):
        Robot.__init__(self)
        BehaviorClient.__init__(self, uid, conversation_id, namespace)
        self.character = os.environ["HR_CHARACTER"]
        tts_config_file = os.environ["TTS_CONFIG_FILE"]
        with open(tts_config_file) as f:
            self.tts_config = yaml.safe_load(f)
        self.tts_client = TTSClient(format=AUDIO_FORMAT)

    def get_tts_param(self, lang):
        return self.tts_config["voices"][self.character][lang].split(":")

    def _execute_tts_result(self, response, audio_clip):
        success = False
        try:
            error = response.response.get("error")
            if error:
                logger.error(error)
            else:
                if audio_clip:
                    self.robot_speaking.set()
                    if not audio_clip.startswith("/"):
                        audio_clip = os.path.join(DATA_DIR, audio_clip)
                    playback.play(AudioSegment.from_wav(audio_clip))
                else:
                    tts_cache_id = response.response["id"]
                    format = response.response["format"]
                    audiofile = "%s.%s" % (tts_cache_id, format)
                    success = response.write(audiofile)
                    if success:
                        self.robot_speaking.set()
                        if format == "mp3":
                            if STREAM_AUDIO == "1":
                                playback.stream_audio(audiofile)
                            else:
                                playback.play(AudioSegment.from_mp3(audiofile))
                        elif format == "wav":
                            if STREAM_AUDIO == "1":
                                logger.error("Wave audio streaming is not supported")
                            else:
                                playback.play(AudioSegment.from_wav(audiofile))
                        os.remove(audiofile)
        except Exception as ex:
            logger.error("TTS error %s", ex)
        finally:
            self.robot_speaking.clear()
        return success

    def say(self, text, lang="en-US"):
        try:
            vendor, voice = self.get_tts_param(lang)
            response = self.tts_client.tts(text, vendor=vendor, voice=voice)
        except Exception as ex:
            logger.error("TTS error %s", ex)
            return False
        return self._execute_tts_result(response)

    async def async_say(self, text, lang="en-US", audio_clip=None):
        try:
            vendor, voice = self.get_tts_param(lang)
            response = await self.tts_client.async_tts(text, vendor=vendor, voice=voice)
        except Exception as ex:
            logger.error("TTS error %s", ex)
            return False
        return self._execute_tts_result(response, audio_clip)

    async def on_detect_speech(self, message):
        logger.info("detect_speech %s", message)
        await self.sio.emit("ack", "detect_speech")
        result = await self.wait_for_speech(
            message["speech_timeout"],
            message["lang"],
            message.get("beepsound", False),
            message.get("standby", False),
        )
        self.empty_speech_queue()
        if result:
            return ActionResult(
                success=True, event="detect_speech", message=result
            ).dict()
        else:
            return ActionResult(success=False, event="detect_speech").dict()

    async def on_say(self, message):
        logger.info("On say %s", message)
        await self.sio.emit("ack", "say")
        logger.warning("Say %r", message["text"])
        lang = get_language_code(message["lang"])
        success = await self.async_say(
            message["text"], lang=lang, audio_clip=message["audio_clip"]
        )

        return ActionResult(success=success, event="say").dict()
