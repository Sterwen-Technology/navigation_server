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
import threading
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
version = "0.6"


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


def run_cmd(cmd: str):
    args = shlex.split(cmd)
    try:
        r = subprocess.run(args, capture_output=True, encoding='utf-8')
    except Exception as e:
        _logger.error('SendCmd %s error %s' % (args[0], e))
        return -1, str(e)
    if r.returncode != 0:
        _logger.error("Agent error for command:%s" % args[0])
        return r.returncode, 'Process return code %s' % r.returncode
    lines = r.stdout.split('\n')
    return 0, lines


def run_systemd(cmd: str, service: str):
    if cmd not in ('start', 'stop', 'restart', 'status'):
        raise ValueError
    args = ['systemctl', cmd, service]
    try:
        r = subprocess.run(args, capture_output=True, encoding='utf-8')
    except Exception as e:
        _logger.error("systemctl execution error: %s" % e)
        return -1
    _logger.info("systemctl return code:%d" % r.returncode)
    lines = r.stdout.split('\n')
    _logger.info("stdout=%s" % lines)
    return r.returncode, lines


class AgentExecutor(threading.Thread):

    def __init__(self, cmd: str):
        self._cmd = cmd
        super().__init__()

    def run(self):
        time.sleep(3.0)
        run_cmd(self._cmd)


class AgentServicerImpl(AgentServicer):

    def SendCmdMultipleResp(self, request, context):
        cmd = request.cmd
        _logger.info("Agent send cmd multiple responses:%s" % cmd)
        return_code, lines = run_cmd(cmd)
        if return_code != 0:
            resp = AgentResponse()
            resp.err_code = return_code
            resp.resp = lines
            yield resp
            return
        first_resp = True
        for l_resp in lines:
            resp = AgentResponse()
            if first_resp:
                resp.err_code = 0
                first_resp = False
            resp.resp = l_resp
            _logger.debug("Resp:%s" % l_resp)
            yield resp
        return

    def SendCmdSingleResp(self, request, context):
        cmd = request.cmd
        _logger.info("Agent send cmd simple responses:%s" % cmd)
        return_code, lines = run_cmd(cmd)
        if isinstance(lines, list):
            line = lines[0]
        else:
            line = lines
        resp = AgentResponse()
        resp.err_code = return_code
        resp.resp = line
        return resp

    def SendCmdNoResp(self, request, context):
        cmd = request.cmd
        _logger.info("Agent send cmd no responses:%s" % cmd)
        executor = AgentExecutor(cmd)
        resp = AgentResponse()
        resp.err_code = 0
        executor.start()
        return resp

    def SystemdCmd(self, request, context):
        cmd = request.cmd
        service = request.service
        _logger.info("Agent systemctl %s %s" % (cmd, service))
        return_code, lines = run_systemd(cmd, service)
        resp = AgentResponseML()
        resp.err_code = return_code
        if len(lines) > 0:
            for l in lines:
                resp.lines.add(l)
        else:
            resp.lines.add("%s %s return code:%d" % (cmd, service, return_code))
        return resp


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
