#!/usr/bin/env python3

import asyncio
import atexit
import cmd
import logging
import os
import readline
import shlex

from dotenv import load_dotenv

load_dotenv(dotenv_path=".envcli")

from btree_client.robot import GenericRobot  # noqa

logger = logging.getLogger(__name__)

ASR_CONTEXT = os.environ.get("ASR_CONTEXT", "").split(",")


class CLI(cmd.Cmd, object):

    HISTFILE_SIZE = 10000

    def __init__(self, args):
        super(CLI, self).__init__()
        self.prompt = "robot > "
        self.uid = args.uid
        self.robot = GenericRobot(args.uid)
        if ASR_CONTEXT:
            self.robot.set_asr_context(ASR_CONTEXT)
        self.robot.loop = asyncio.get_event_loop()
        self.token = os.environ.get(
            "BTREE_SERVER_TOKEN", "aJyq2Z1f3RHFJ4BfqdICRAD9QyVDr3bcG62C1Ev2oSc"
        )
        user_dir = os.path.expanduser(f"~/.hrsdk/user/{self.uid}")
        self.histfile = os.path.join(user_dir, ".cli_history")
        self.input_lines = []

    def emptyline(self):
        pass

    def preloop(self):
        if readline and os.path.exists(self.histfile):
            readline.read_history_file(self.histfile)

    def postloop(self):
        if readline:
            readline.set_history_length(self.HISTFILE_SIZE)
            dir = os.path.dirname(self.histfile)
            if not os.path.isdir(dir):
                os.makedirs(dir)
            readline.write_history_file(self.histfile)

    def postcmd(self, stop, line):
        if not stop:
            self.input_lines.append(line)
        return stop

    def do_lang(self, lang):
        self.robot.set_lang(lang)

    def do_run(self, line):
        try:
            trees = [t.strip() for t in shlex.split(line) if t.strip()]
        except ValueError as ex:
            logger.error(ex)
            return
        if trees:
            try:
                self.robot.loop.run_until_complete(
                    self.robot.connect_socket(self.token, trees)
                )
            except Exception as ex:
                logger.error(ex)
            except KeyboardInterrupt:
                logger.info("Disconnecting btree...")
                self.robot.loop = asyncio.get_event_loop()
                self.robot.loop.run_until_complete(self.robot.sio.disconnect())
        else:
            logger.warning("No trees to run")

    def do_q(self, line=None):
        """
        Quit interactive console
        """
        return True


if __name__ == "__main__":
    import argparse
    import sys

    import coloredlogs

    parser = argparse.ArgumentParser()
    parser.add_argument("--uid", default="default", help="user id")
    parser.add_argument(
        "--verbose", action="store_true", default=False, help="verbose logging"
    )
    args = parser.parse_args()

    if "coloredlogs" in sys.modules and os.isatty(2):
        formatter_str = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
    if args.verbose:
        coloredlogs.install(logging.INFO, fmt=formatter_str)
    else:
        coloredlogs.install(logging.WARN, fmt=formatter_str)

    cli = CLI(args)
    atexit.register(cli.do_q)
    try:
        cli.cmdloop()
    except KeyboardInterrupt:
        cli.postloop()
    except Exception as ex:
        cli.postloop()
        logger.exception(ex)
