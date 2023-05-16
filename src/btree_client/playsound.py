import logging
import sys
import threading
import wave

import pyaudio

from btree_client.utils import noalsaerr

logger = logging.getLogger(__name__)


class SoundFile(object):
    def __init__(self):
        self._interrupt = threading.Event()
        self.CHUNK = 1024
        with noalsaerr():
            self.p = pyaudio.PyAudio()

    async def async_play(self, wavfile):
        if wavfile.endswith(".mp3"):
            raise ValueError("mp3 is not supported")
        self._interrupt.clear()
        wf = wave.open(wavfile, "rb")
        stream = self.p.open(
            format=self.p.get_format_from_width(wf.getsampwidth()),
            channels=wf.getnchannels(),
            rate=wf.getframerate(),
            output=True,
        )
        try:
            data = wf.readframes(self.CHUNK)
            while not self._interrupt.is_set() and len(data) > 0:
                stream.write(data)
                data = wf.readframes(self.CHUNK)
        finally:
            stream.stop_stream()
            stream.close()
        wf.close()

    def play(self, wavfile):
        if wavfile.endswith(".mp3"):
            raise ValueError("mp3 is not supported")
        self._interrupt.clear()
        wf = wave.open(wavfile, "rb")
        stream = self.p.open(
            format=self.p.get_format_from_width(wf.getsampwidth()),
            channels=wf.getnchannels(),
            rate=wf.getframerate(),
            output=True,
        )
        samplewidth = wf.getsampwidth()
        try:
            data = wf.readframes(self.CHUNK)
            while len(data) > 0 and not self._interrupt.is_set():
                stream.write(data)
                data = wf.readframes(self.CHUNK)
                if len(data) < samplewidth * self.CHUNK:
                    stream.write(chr(0) * (samplewidth * self.CHUNK - len(data)))
        except Exception as ex:
            logger.error(ex)
        finally:
            stream.stop_stream()
            stream.close()
        wf.close()

    def interrupt(self):
        self._interrupt.set()
        logger.warning("Sound is interrupted")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Plays a wave file.\n\nUsage: %s filename.wav" % sys.argv[0])
        sys.exit(-1)
    soundfile = SoundFile()
    job = threading.Timer(0, soundfile.play, (sys.argv[1],))
    job.daemon = True
    job.start()
    threading.Timer(1, soundfile.interrupt).start()
    job.join()
