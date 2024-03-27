#-------------------------------------------------------------------------------
# Name:        agent_service.py
# Purpose:     gRPC service for the local agent
#
# Author:      Laurent Carré
#
# Created:     26/02/2024
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2024
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------


import subprocess
import shlex
import threading
import logging
import time

from generated.agent_pb2 import *
from generated.agent_pb2_grpc import *
from router_common import GrpcService

_logger = logging.getLogger("ShipDataServer." + __name__)


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
    _logger.debug("systemctl return code:%d" % r.returncode)
    lines = r.stdout.split('\n')
    _logger.debug("stdout=%s" % lines)
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
        if len(lines) > 1:
            resp.lines.extend(lines)
        else:
            resp.lines.extend(["%s %s return code:%d" % (cmd, service, return_code)])
        return resp


class AgentService(GrpcService):

    def __init__(self, opts):
        super().__init__(opts)

    def finalize(self):
        super().finalize()
        add_AgentServicer_to_server(AgentServicerImpl(), self.grpc_server)
