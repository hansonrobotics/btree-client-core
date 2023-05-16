import json
import logging
import os
import re
from contextlib import contextmanager

from slugify import slugify

from btree_client.schemas import Tree

logger = logging.getLogger(__name__)

# https://cloud.google.com/translate/docs/languages
# https://docs.microsoft.com/azure/cognitive-services/speech-service/language-support#text-to-speech
LANGUAGE_BCP47_CODES = {
    "Arabic": "ar-SA",
    "Cantonese": "yue-Hant-HK",
    "Chinese": "cmn-Hans-CN",
    "Czech": "cs-CZ",
    "English": "en-US",
    "French": "fr-FR",
    "German": "de-DE",
    "Hindi": "hi-IN",
    "Hungarian": "hu-HU",
    "Italian": "it-IT",
    "Japanese": "ja-JP",
    "Korean": "ko-KR",
    "Mandarin": "cmn-Hans-CN",
    "Norwegian": "no-NO",
    "Polish": "pl-PL",
    "Russian": "ru-RU",
    "Spanish": "es-ES",
    "ar": "ar-SA",
    "cs": "cs-CZ",
    "de": "de-DE",
    "en": "en-US",
    "es": "es-ES",
    "fr": "fr-FR",
    "hi": "hi-IN",
    "hk": "yue-Hant-HK",
    "hu": "hu-HU",
    "it": "it-IT",
    "ja": "ja-JP",
    "ko": "ko-KR",
    "no": "no-NO",
    "pl": "pl-PL",
    "ru": "ru-RU",
    "zh": "cmn-Hans-CN",
}

BEHAVIOR_PROJECT_DIR = os.environ.get("BEHAVIOR_PROJECT_DIR", ".")


@contextmanager
def noalsaerr():
    """Suppress ALSA error messages
    https://stackoverflow.com/questions/7088672/pyaudio-working-but-spits-out-error-messages-each-time
    """
    import sys

    if sys.platform != "linux":
        yield
    else:
        from ctypes import CFUNCTYPE, c_char_p, c_int, cdll

        def py_error_handler(filename, line, function, err, fmt):
            pass

        c_error_handler = CFUNCTYPE(None, c_char_p, c_int, c_char_p, c_int, c_char_p)(
            py_error_handler
        )
        asound = cdll.LoadLibrary("libasound.so")
        asound.snd_lib_error_set_handler(c_error_handler)
        yield
        asound.snd_lib_error_set_handler(None)


def to_number(i):
    if isinstance(i, int) or isinstance(i, float):
        return i
    try:
        if "." in i:
            return float(i)
        else:
            return int(i)
    except (TypeError, ValueError):
        return float(i)


def iterable(obj):
    try:
        iter(obj)
        return not isinstance(obj, str)
    except TypeError:
        pass
    return False


def to_list(obj):
    if obj is None:
        return []
    if iterable(obj):
        return obj
    else:
        return [obj]


def get_language_code(lang, default="en-US"):
    if lang == "-" or lang == "":
        lang = default
    return LANGUAGE_BCP47_CODES.get(lang, lang)


def get_lock_name(tree):
    return "%s_lock" % slugify(tree, separator="_")


def load_tree_model(tree: str):
    tree = slugify(tree, lowercase=False)
    tree_file = os.path.join(BEHAVIOR_PROJECT_DIR, f"{tree}.tree.json")
    if not os.path.isfile(tree_file):
        logger.warning("Can't load tree %r", tree)
        return
    with open(tree_file) as f:
        return Tree(**json.load(f))


def norm_text(text):
    text = re.sub(r"[^a-zA-Z0-9 ]", "", text)
    norm = " ".join(text.split())
    norm = norm.lower()
    return norm
