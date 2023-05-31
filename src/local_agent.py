#-------------------------------------------------------------------------------
# Name:        local_agent.py
# Purpose:     top module for the navigation server
#
# Author:      Laurent Carré
#
# Created:     30/05/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import sys
import logging
import os
import time
from argparse import ArgumentParser
import subprocess
import shlex
import signal

from generated.agent_pb2 import *
from generated.agent_pb2_grpc import *

from nmea_routing.server_common import NavigationGrpcServer


def _parser():
    p = ArgumentParser(description=sys.argv[0])

    p.add_argument('-p', '--port', action='store', type=int, default=4506)
    p.add_argument('-n', '--name', type=str, default='NavigationAgentServer')
    p.add_argument('-d', '--working_dir', action='store', type=str)

    return p


parser = _parser()
_logger = logging.getLogger("ShipDataServer")
default_base_dir = "/mnt/meaban/Sterwen-Tech-SW/navigation_server"
version = "0.5"


class Options(object):
    def __init__(self, p):
        self.parser = p
        self.options = None

    def __getattr__(self, name):
        if self.options is None:
            self.options = self.parser.parse_args()
        try:
            return getattr(self.options, name)
        except AttributeError:
            raise AttributeError(name)

    def __getitem__(self, item):
        return self.__getattr__(item)

    def get(self, attr, type, default):
        return self.__getattr__(attr)


def run_cmd(args: list):
    try:
        r = subprocess.run(args, capture_output=True, encoding='utf-8')
    except Exception as e:
        _logger.error('SendCmd %s error %s' % (args[0], e))
        return [str(e)]
    if r.returncode != 0:
        _logger.error("Agent error for command:%s" % args[0])
        return ['Process return code %s' % r.returncode]
    lines = r.stdout.split('\n')
    return lines


class AgentServicerImpl(AgentServicer):

    def SendCmd(self, request, context):
        cmd = request.cmd
        _logger.info("Agent send cmd:%s" % cmd)
        args = shlex.split(cmd)
        lines = run_cmd(args)
        for l_resp in lines:
            resp = AgentResponse()
            resp.resp = l_resp
            _logger.debug("Resp:%s" % l_resp)
            yield resp
        return


class AgentServer(NavigationGrpcServer):

    def __init__(self, options):

        super().__init__(options)
        add_AgentServicer_to_server(AgentServicerImpl(), self._grpc_server)


def main():
    opts = Options(parser)
    if opts.working_dir is not None:
        os.chdir(opts.working_dir)
    else:
        if os.getcwd() != default_base_dir:
            os.chdir(default_base_dir)
    # print("Current directory", os.getcwd())
    # set log for the configuration phase
    loghandler = logging.StreamHandler()
    logformat = logging.Formatter("%(asctime)s | [%(levelname)s] %(message)s")
    loghandler.setFormatter(logformat)
    _logger.addHandler(loghandler)
    _logger.setLevel('INFO')
    _logger.info("Starting Navigation local agent %s - copyright Sterwen Technology 2021-2023" % version)

    server = AgentServer(opts)
    server.start()
    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        server.stop()
    server.join()


if __name__ == '__main__':
    main()
