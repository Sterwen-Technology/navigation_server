#-------------------------------------------------------------------------------
# Name:        nmea_server_client
# Purpose:     client for the grpc NMEA server
#
# Author:      Laurent Carré
#
# Created:     30/03/2025
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging

from navigation_server.router_common import GrpcClient, GrpcAccessException, ServiceClient
from navigation_server.generated.nmea_messages_pb2 import nmea_msg, server_cmd, server_resp
from navigation_server.generated.nmea_server_pb2_grpc import NMEAServerStub


class GrpcNmeaServerClient(ServiceClient):

    def __init__(self):
        super().__init__(NMEAServerStub)

    def status(self):
        cmd = server_cmd()
        cmd.cmd = "status"
        return self._server_call(self._stub.status, cmd, None)

    def getNMEA(self):
        cmd = server_cmd()
        cmd.cmd = "NMEA2000"
        for msg in self._server_call_multiple(self._stub.getNMEA, cmd, None):
            yield msg


if __name__ == "__main__":
    loghandler = logging.StreamHandler()
    logformat = logging.Formatter("%(asctime)s | [%(levelname)s] %(message)s")
    loghandler.setFormatter(logformat)
    top_logger = logging.getLogger("ShipDataClient")
    top_logger.addHandler(loghandler)
    top_logger.setLevel('INFO')
    client = GrpcNmeaServerClient()
    server = GrpcClient.get_client("127.0.0.1:4502")
    server.add_service(client)
    server.connect()
    resp = client.status()
    print(resp)
    while True:
        try:
            for nmea_msg in client.getNMEA():
                n2k_msg_pb = nmea_msg.N2K_msg
                # n2k_msg = NMEA2000Msg(n2k_msg_pb.pgn, protobuf=n2k_msg_pb)
                print(n2k_msg_pb.pgn, n2k_msg_pb.sa)
        except GrpcAccessException as e:
            print(e)
            break
        except KeyboardInterrupt:
            break


