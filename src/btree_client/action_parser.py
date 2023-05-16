import logging
import re
import xml.etree.ElementTree as etree

logger = logging.getLogger(__name__)


class Pattern(object):
    def __init__(self, pattern):
        self.pattern = pattern
        self.pattern_re = re.compile(self.pattern, re.DOTALL | re.UNICODE)

    def match(self, text):
        return self.pattern_re.match(text)

    def get_nodes(self, match):
        return NotImplemented

    def __repr__(self):
        return self.__class__.__name__


class MarkPattern(Pattern):
    def __init__(self):
        super(MarkPattern, self).__init__(r"^(.*?)(\|)([^\|]+)\2(.*)$")

    def get_nodes(self, match):
        name = match.group(3)
        name = name.strip()
        el = etree.Element("mark")
        el.set("name", name)
        return (el,)


class ActionParser(object):
    def __init__(self):
        self.patterns = []
        self.build_patterns()
        self.recognized_nodes = {}
        self.counter = 0
        self.sep = "0x1f"

    def reset(self):
        self.counter = 0
        self.recognized_nodes.clear()

    def build_patterns(self):
        self.patterns.append(MarkPattern())

    def add_recognized_nodes(self, node):
        id = "sss{}eee".format(self.counter)
        self.recognized_nodes[id] = node
        self.counter += 1
        return id

    def recover_recognized_nodes(self, text):
        tokens = text.split(self.sep)
        nodes = []
        for token in tokens:
            if token in self.recognized_nodes:
                node = self.recognized_nodes.get(token)
                nodes.append(node)
            else:
                nodes.append(token)
        return nodes

    def parse(self, text):
        if not text:
            return []
        if not isinstance(text, str):
            text = text.decode("utf-8")
        text = text.strip()
        self.reset()
        pattern_index = 0
        while pattern_index < len(self.patterns):
            pattern = self.patterns[pattern_index]
            match = pattern.match(text)

            # Search all the matches then try the next pattern
            if not match:
                pattern_index += 1
                continue

            try:
                nodes = pattern.get_nodes(match)
            except Exception as ex:
                logger.error(ex)
                nodes = [""]  # replace the pattern with an empty string
            place_holders = []
            for node in nodes:
                if not isinstance(node, str):
                    id = self.add_recognized_nodes(node)
                    place_holders.append(id)
                else:
                    place_holders.append(node)
            text = "{}{}{}{}{}".format(
                match.group(1),
                self.sep,
                self.sep.join(place_holders),
                self.sep,
                match.groups()[-1],
            )

        nodes = self.recover_recognized_nodes(text)
        return nodes


if __name__ == "__main__":
    action_parser = ActionParser()
    print(action_parser.parse("hello |smile|"))
    print(action_parser.parse("hello there"))
