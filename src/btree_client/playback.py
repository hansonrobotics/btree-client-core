import logging
import time

import simpleaudio

try:
    from bluepy.btle import ADDR_TYPE_PUBLIC, Peripheral
except Exception:
    pass
    
logger = logging.getLogger(__name__)

AUDIO_START_BUFFERING = 0  # noqa
AUDIO_STOP_BUFFERING = 1
AUDIO_PLAY_STREAM = 2


def play(seg):
    playback = simpleaudio.play_buffer(
        seg.raw_data,
        num_channels=seg.channels,
        bytes_per_sample=seg.sample_width,
        sample_rate=seg.frame_rate,
    )
    try:
        playback.wait_done()
    except KeyboardInterrupt:
        playback.stop()
    else:
        return
    logger.error("Audio finished")


def stream_audio(audiofile):
    peripheral = Peripheral("f4:12:fa:e5:b2:2e", ADDR_TYPE_PUBLIC)
    peripheral.setMTU(153)
    service = peripheral.getServiceByUUID("0000180d-0000-1000-8000-00805f9b34fb")
    ble_audio_cmd_char = service.getCharacteristics(
        "00000001-0000-1000-8000-00805f9b34fb"
    )[0]
    ble_audio_data_char = service.getCharacteristics(
        "00000004-0000-1000-8000-00805f9b34fb"
    )[0]

    file_p = open(audiofile, "rb")
    msg = file_p.read(150)
    ble_audio_cmd_char.write(AUDIO_PLAY_STREAM.to_bytes(1, "big"))
    while msg:
        ble_audio_data_char.write(msg)
        time.sleep(0.008)
        msg = file_p.read(150)
    ble_audio_cmd_char.write(AUDIO_STOP_BUFFERING.to_bytes(1, "big"))


if __name__ == "__main__":
    import sys

    from pydub import AudioSegment

    if len(sys.argv) < 2:
        print("Plays a wave file.\n\nUsage: %s filename.wav" % sys.argv[0])
        sys.exit(-1)
    fname = sys.argv[1]
    seg = AudioSegment.from_wav(fname)
    play(seg)
