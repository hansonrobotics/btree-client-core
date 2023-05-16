#!/usr/bin/env python3
#
# Copyright (c) 2021 Hanson Robotics.
#
# This file is part of Hanson AI.
# See https://www.hansonrobotics.com/hanson-ai for further info.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import json
import logging
from pathlib import Path

import vosk

from btree_client.asr import ResumableMicrophoneStream, SpeechRecognizer

logger = logging.getLogger(__name__)
vosk.SetLogLevel(-1)


class VoskSpeechRecognizer(SpeechRecognizer):
    """Provides an recognition service for specific language"""

    @staticmethod
    def load_models(model_dir):
        models = {}  # language -> model
        for model_path in Path(model_dir).iterdir():
            if not model_path.is_dir():
                continue
            try:
                models[str(model_path.name)] = vosk.Model(model_path=str(model_path))
            except Exception as ex:
                logger.error("Model load failed with exception %s", ex)
        return models

    def __init__(self, robot, models):
        super(VoskSpeechRecognizer, self).__init__(robot)
        self.models = models

    def _transcribe_streaming(self, stream, lang):
        logger.info("Transcribe streaming %s", lang)
        if lang not in self.models:
            raise ValueError("Language %r is not supported" % lang)
        model = self.models[lang]
        rec = vosk.KaldiRecognizer(model, self.sample_rate)
        rec.SetMaxAlternatives(5)
        for data in stream.generator():
            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                if result["alternatives"]:
                    # If one of alternatives are no speech,
                    # ignore as likely it will be inacurate
                    valid = all([r["text"] != "" for r in result["alternatives"]])
                    if valid:
                        alt = result["alternatives"][0]
                        self.speech_cb(alt["text"], alt["confidence"] / 100, lang)
                        stream.closed = True  # close the stream after the first result
            else:
                result = json.loads(rec.PartialResult())
                if result["partial"]:
                    self.interim_cb(result["partial"], 0, lang)

    def start(self, lang):
        logger.info("Starting speech recognition")
        self.streamer = ResumableMicrophoneStream(
            self.sample_rate, self.chunk_size, self.stream_callback
        )
        try:
            with self.streamer as stream:
                while not stream.closed:
                    stream.audio_input = []
                    self._transcribe_streaming(stream, lang)
        except Exception as ex:
            logger.error(ex)
        self.stop.set()
        logger.info("Stopped speech recognition")


if __name__ == "__main__":
    import coloredlogs

    coloredlogs.install(level=logging.DEBUG)
    model_dir = "/home/wenwei/workspace/hrsdk_configs/models/offline_asr"
    from btree_client.robot import Robot

    robot = Robot("default")
    VoskSpeechRecognizer(robot, model_dir).start("en-US")
