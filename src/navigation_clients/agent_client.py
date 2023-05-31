#-------------------------------------------------------------------------------
# Name:        Agent Client
# Purpose:     Agent client interface via GPRC for navigation server
#
# Author:      Laurent Carré
#
# Created:     31/05/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging

from generated.agent_pb2 import *
from generated.agent_pb2_grpc import *
from utilities.protobuf_utilities import GrpcAccessException

_logger = logging.getLogger("ShipDataClient")


class AgentClient:

    def __init__(self, address):
        self._channel = grpc.insecure_channel(address)
        self._stub = AgentStub(self._channel)
        self._address = address
        self._req_id = 0
        _logger.info("Console on agent server %s" % address)

    def send_cmd(self, cmd):
        request = AgentMsg()
        request.id = self._req_id
        self._req_id += 1
        request.cmd = cmd
        try:
            for resp in self._stub.SendCmd(request):
                yield resp.resp
        except grpc.RpcError as err:
            if err.code() != grpc.StatusCode.UNAVAILABLE:
                _logger.info("Server not accessible")
            else:
                _logger.error("SendCmd - Error accessing server:%s" % err)
            raise GrpcAccessException


def main():
    loghandler = logging.StreamHandler()
    logformat = logging.Formatter("%(asctime)s | [%(levelname)s] %(message)s")
    loghandler.setFormatter(logformat)
    _logger.addHandler(loghandler)
    _logger.setLevel('INFO')
    client = AgentClient("localhost:4506")
    try:
        for r in client.send_cmd('ls'):
            print(r)
    except GrpcAccessException:
        _logger.error("No action")


if __name__ == '__main__':
    main()
