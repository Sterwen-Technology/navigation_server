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

from navigation_server.generated.agent_pb2_grpc import *
from navigation_server.router_common import GrpcAccessException
from router_common.client_common import ServiceClient, GrpcClient

_logger = logging.getLogger("ShipDataClient." + __name__)


class AgentClient(ServiceClient):
    """
    Brief summary of what the AgentClient class does.

    AgentClient is a specialized client that interacts with an agent server to
    send commands and retrieve responses. It provides methods to handle single
    response, multiple responses, systemd commands, and network commands
    via server calls.

    Attributes
    ----------
    None
    """
    def __init__(self):
        super().__init__(AgentStub)

    def send_cmd_multiple_resp(self, cmd):
        """
        send_cmd_multiple_resp(cmd)

        Sends a command to the server and yields multiple responses asynchronously. The function
        creates a request message with the specified command, invokes the server call method, and
        yields each response received from the server.

        Parameters:
        cmd: The command to be sent to the server.

        Yields:
        The response received from the server for the given command.
        """
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

#
#  for testing
#
def main():
    loghandler = logging.StreamHandler()
    logformat = logging.Formatter("%(asctime)s | [%(levelname)s] %(message)s")
    loghandler.setFormatter(logformat)
    top_logger = logging.getLogger("ShipDataClient")
    top_logger.addHandler(loghandler)
    top_logger.setLevel('INFO')
    server = GrpcClient("192.168.1.30:4506")
    client = AgentClient()
    server.add_service(client)
    server.connect()
    try:
        for r in client.send_cmd_multiple_resp('ls'):
            print(r)
    except GrpcAccessException:
        _logger.error("No action")


if __name__ == '__main__':
    main()
