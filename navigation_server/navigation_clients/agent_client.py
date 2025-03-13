#-------------------------------------------------------------------------------
# Name:        Agent Client
# Purpose:     Agent client interface via GPRC for navigation server
#
# Author:      Laurent Carré
#
# Created:     31/05/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging

import grpc

from navigation_server.generated.agent_pb2 import *
from navigation_server.generated.agent_pb2_grpc import *
from navigation_server.router_common import GrpcAccessException
from .client_common import GrpcClient, ServiceClient

_logger = logging.getLogger("ShipDataClient." + __name__)


class AgentClient(ServiceClient):

    def __init__(self):
        super().__init__(AgentStub)

    def send_cmd_multiple_resp(self, cmd):
        request = AgentMsg()
        request.cmd = cmd
        for resp in self._server_call_multiple(self._stub.SendCmdMultipleResp, request, None):
            yield resp.resp

    def send_cmd_single_resp(self, cmd):
        request = AgentMsg()
        request.cmd = cmd
        return self._server_call(self._stub.SendCmdSingleResp, request, None).resp

    def send_cmd_no_resp(self, cmd):
        request = AgentMsg()
        request.cmd = cmd
        return self._server_call(self._stub.SendCmdNoResp, request, None).resp

    def systemd_cmd(self, cmd, service):
        request = SystemdCmdMsg()
        request.cmd = cmd
        request.service = service
        return self._server_call(self._stub.SystemdCmd, request, None).lines

    def network_cmd(self, cmd, interface):
        request = NetworkCmdMsg()
        request.cmd = cmd
        request.interface = interface
        _logger.info(f"Agent client network cmd {cmd} on {interface}")
        return self._server_call(self._stub.NetworkCmd, request, None).resp


def main():
    loghandler = logging.StreamHandler()
    logformat = logging.Formatter("%(asctime)s | [%(levelname)s] %(message)s")
    loghandler.setFormatter(logformat)
    _logger.addHandler(loghandler)
    _logger.setLevel('INFO')
    client = AgentClient("192.168.1.30:4506")
    try:
        for r in client.send_cmd('ls'):
            print(r)
    except GrpcAccessException:
        _logger.error("No action")


if __name__ == '__main__':
    main()
