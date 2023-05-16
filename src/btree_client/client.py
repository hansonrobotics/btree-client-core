import logging
import os
import uuid
from abc import ABCMeta, abstractmethod

import socketio

from btree_client.schemas import ActionResult
from btree_client.utils import get_language_code, to_list

logger = logging.getLogger(__name__)


class BehaviorClient(socketio.AsyncClientNamespace, metaclass=ABCMeta):
    def __init__(self, uid, conversation_id=None, namespace="/"):
        super(BehaviorClient, self).__init__(namespace=namespace)
        self.uid = uid
        self.conversation_id = conversation_id
        if self.conversation_id is None:
            if self.uid == 'default':
                self.conversation_id = 'default'
            else:
                self.conversation_id = str(uuid.uuid4())
        self.running_trees = []
        self.lang = "en-US"
        self.finished = []
        self.sio = socketio.AsyncClient(reconnection=False)
        self.sio.register_namespace(self)

    def set_lang(self, lang):
        self.lang = get_language_code(lang)

    async def pre_start(self):
        self.finished = []

    async def connect_socket(self, token, trees=[]):
        BTREE_BASE_URL = os.environ.get("BTREE_BASE_URL", "http://localhost:9200")

        await self.pre_start()
        await self.sio.connect(
            f"{BTREE_BASE_URL}/ws?uid={self.uid}&conversation_id={self.conversation_id}",
            headers={"token": token},
            socketio_path="/ws/socket.io",
            wait_timeout=10,
        )
        logger.warning("connected %s, trees %r", self.sio.connected, trees)
        if 'probe' not in trees:
            trees.append('probe')
            logger.warning("Added probe tree")
        await self._on_connect(trees)
        # set parameters after connection
        await self.sio.emit("set", {"lang": self.lang})
        await self.sio.wait()

    async def close(self):
        self.running_trees = []
        await self.sio.disconnect()
        return True

    async def on_error(self, message):
        logger.error("Error %s", message)
        await self.sio.disconnect()

    async def on_finish(self, message):
        tree = message["tree"]
        logger.warning("Finished tree %r", tree)
        self.finished.append(tree)
        if tree in self.running_trees:
            self.running_trees.remove(tree)
        if len(self.running_trees) == 0:
            logger.warning("All trees are finished %s", self.finished)
            await self.sio.disconnect()

    async def run_tree(self, tree):
        if tree not in self.running_trees:
            if self.sio.connected:
                logger.warning("Starting tree %r", tree)
                await self.sio.emit("start", {"tree": tree})
                self.running_trees.append(tree)
            else:
                logger.error("Can't start tree %r. Socket connection has not established", tree)

    async def _on_connect(self, trees):
        if trees:
            for tree in to_list(trees):
                await self.run_tree(tree)
        else:
            logger.warning("No trees to run")
            await self.sio.disconnect()
        logger.info("connection established")

    async def on_disconnect(self):
        logger.info("disconnected from server")

    async def on_timeline(self, message):
        return ActionResult(success=True, event="timelne").dict()

    @abstractmethod
    async def on_say(self, message) -> ActionResult:
        pass

    async def on_set(self, message):
        return ActionResult(success=True, event="set").dict()

    @abstractmethod
    async def on_detect_speech(self, message) -> ActionResult:
        pass

    async def on_probe(self, message):
        return ActionResult(success=True, event="probe", message={}).dict()
