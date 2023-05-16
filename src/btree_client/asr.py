import logging
import queue
import threading
import time
from abc import ABCMeta, abstractmethod

import pyaudio

from btree_client.utils import noalsaerr

STREAMING_LIMIT = 240000  # 4 minutes

logger = logging.getLogger(__name__)


def get_current_time():
    """Return Current Time in MS."""

    return int(round(time.time() * 1000))


class ResumableMicrophoneStream(object):
    """Opens a recording stream as a generator yielding the audio chunks."""

    def __init__(self, rate, chunk_size, stream_callback):
        self._rate = rate
        self.chunk_size = chunk_size
        self._num_channels = 1
        self._buff = queue.Queue()
        self.closed = True
        self.start_time = get_current_time()
        self.restart_counter = 0
        self.audio_input = []
        self.last_audio_input = []
        self.result_end_time = 0
        self.is_final_end_time = 0
        self.final_request_end_time = 0
        self.bridging_offset = 0
        self.last_transcript_was_final = False
        self.new_stream = True
        with noalsaerr():
            self._audio_interface = pyaudio.PyAudio()
        self._audio_stream = self._audio_interface.open(
            format=pyaudio.paInt16,
            channels=self._num_channels,
            rate=self._rate,
            input=True,
            frames_per_buffer=self.chunk_size,
            # Run the audio stream asynchronously to fill the buffer object.
            # This is necessary so that the input device's buffer doesn't
            # overflow while the calling thread makes network requests, etc.
            stream_callback=stream_callback,
        )

    def __enter__(self):

        self.closed = False
        return self

    def __exit__(self, type, value, traceback):

        self._audio_stream.stop_stream()
        self._audio_stream.close()
        self.closed = True
        # Signal the generator to terminate so that the client's
        # streaming_recognize method will not block the process termination.
        self._buff.put(None)
        self._audio_interface.terminate()

    def generator(self):
        """Stream Audio from microphone to API and to local buffer"""

        while not self.closed:
            data = []

            if self.new_stream and self.last_audio_input:

                chunk_time = STREAMING_LIMIT / len(self.last_audio_input)

                if chunk_time != 0:

                    if self.bridging_offset < 0:
                        self.bridging_offset = 0

                    if self.bridging_offset > self.final_request_end_time:
                        self.bridging_offset = self.final_request_end_time

                    chunks_from_ms = round(
                        (self.final_request_end_time - self.bridging_offset)
                        / chunk_time
                    )

                    self.bridging_offset = round(
                        (len(self.last_audio_input) - chunks_from_ms) * chunk_time
                    )

                    for i in range(chunks_from_ms, len(self.last_audio_input)):
                        data.append(self.last_audio_input[i])

                self.new_stream = False

            # Use a blocking get() to ensure there's at least one chunk of
            # data, and stop iteration if the chunk is None, indicating the
            # end of the audio stream.
            chunk = self._buff.get()
            self.audio_input.append(chunk)

            if chunk is None:
                return
            data.append(chunk)
            # Now consume whatever other data's still buffered.
            while True:
                try:
                    chunk = self._buff.get(block=False)

                    if chunk is None:
                        return
                    data.append(chunk)
                    self.audio_input.append(chunk)

                except queue.Empty:
                    break

            yield b"".join(data)


class SpeechRecognizer(object, metaclass=ABCMeta):
    def __init__(self, robot, sample_rate=16000):
        self.sample_rate = sample_rate
        self.chunk_size = int(self.sample_rate / 10)
        self.robot = robot
        self.stop = threading.Event()

    def cancel_user_speaking_event(self):
        logger.warning("Cancel speaking state")
        self.robot.user_speaking.clear()

    def interim_cb(self, transcript, confidence, language):
        if not self.stop.is_set():
            self.robot.user_speaking.set()
            threading.Timer(
                5, self.cancel_user_speaking_event
            )  # 5 seconds of silence cancels the speaking state
            logger.debug("Interrim result: %s, confidence: %s", transcript, confidence)

    def word_cb(self, word, confidence, language):
        logger.debug("Word: %s, confidence: %s", word, confidence)

    def speech_cb(self, transcript, confidence, lang):
        if not self.stop.is_set():
            logger.debug("Final result: %s, confidence: %s", transcript, confidence)
            self.robot.loop.call_soon_threadsafe(
                self.robot.speech_queue.put_nowait,
                {"transcript": transcript, "confidence": confidence, "lang": lang},
            )

    def stream_callback(self, in_data, *args, **kwargs):
        """Continuously collect data from the audio stream, into the buffer."""
        if not self.robot.robot_speaking.is_set():
            self.streamer._buff.put(in_data)
        else:
            in_data = b"\0" * len(in_data)  # replace with 0
            self.streamer._buff.put(in_data)
        if self.stop.is_set():
            logger.info("Stop audio streaming")
            return None, pyaudio.paAbort
        return None, pyaudio.paContinue

    @abstractmethod
    def start(self, lang):
        pass
