import logging

from google.cloud import speech

from btree_client.asr import (
    STREAMING_LIMIT,
    ResumableMicrophoneStream,
    SpeechRecognizer,
    get_current_time,
)

logger = logging.getLogger(__name__)


class GoogleSpeechRecognizer(SpeechRecognizer):
    def __init__(self, robot, context=[]):
        super(GoogleSpeechRecognizer, self).__init__(robot)
        self.phrases = context

    def _transcribe_streaming(self, stream, lang):
        """Streams transcription of the audio steam."""
        client = speech.SpeechClient()

        requests = (
            speech.StreamingRecognizeRequest(audio_content=chunk)
            for chunk in stream.generator()
        )

        # Initialize configurations
        # SpeechContext See
        # https://cloud.google.com/speech/reference/rpc/google.cloud.speech.v1#google.cloud.speech.v1.SpeechContext
        # speech_contexts = speech.SpeechContext(phrases=self.phrases)

        # SpeechAdaptation see
        # https://cloud.google.com/speech-to-text/docs/reference/rest/v1p1beta1/RecognitionConfig#SpeechAdaptation
        phrase_set = speech.PhraseSet(
            name="custom phraseset",
            phrases=[
                speech.PhraseSet.Phrase(value=phrase, boost=20)
                for phrase in self.phrases
            ],
            boost=20,
        )
        speech_adaptation = speech.SpeechAdaptation(phrase_sets=[phrase_set])

        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=self.sample_rate,
            # https://cloud.google.com/speech-to-text/docs/languages
            language_code=lang,
            max_alternatives=1,
            use_enhanced=True,
            # speech_contexts=[speech_contexts],
            enable_automatic_punctuation=True,  # Needs upgrade google.cloud lib
            adaptation=speech_adaptation,
        )
        streaming_config = speech.StreamingRecognitionConfig(
            config=config, interim_results=True
        )

        responses = client.streaming_recognize(streaming_config, requests)
        self.speech_handle_responses(responses, stream)

    def speech_handle_responses(self, responses, stream):
        """Handle the response that is yielded from the cloud server.
        When the response comes, it calculates the compound confidence,
        translates the text if it's set, and then publishes the chat message.
        """
        word_array = []
        for response in responses:
            if not response.results:
                continue

            if get_current_time() - stream.start_time > STREAMING_LIMIT:
                stream.start_time = get_current_time()
                break

            if response.error.code != 0:
                raise RuntimeError("Server error: " + response.error.message)

            top_result = sorted(
                response.results, key=lambda r: r.stability, reverse=True
            )[0]

            # publish interim results
            top_alternative = top_result.alternatives[0]
            confidence = int(100 * top_result.stability)
            if not top_result.is_final:
                self.interim_cb(
                    top_alternative.transcript, confidence, top_result.language_code
                )

            # Publish individual words
            transcript_words = top_alternative.transcript.split(" ")
            new_words = [item for item in transcript_words if item not in word_array]
            word_array.extend(new_words)
            for word in new_words:
                self.word_cb(word.strip(), confidence, top_result.language_code)

            # Assemble the results
            for result in response.results:
                if result.is_final:
                    # no key phrase is spotted then return the first alternative
                    alt = result.alternatives[0]
                    self.speech_cb(alt.transcript, alt.confidence, result.language_code)
                    logger.info("Close audio stream")
                    stream.closed = True  # close the stream after the first asr result
                    return

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
            logger.info(ex)
        self.stop.set()
        logger.info("Stopped speech recognition")


if __name__ == "__main__":
    import coloredlogs

    coloredlogs.install(level=logging.DEBUG)
    from btree_client.robot import Robot

    robot = Robot("default")
    GoogleSpeechRecognizer(robot).start("en-US")
