#-------------------------------------------------------------------------------
# Name:        nmea2k_grpc_coupler.py
# Purpose:     coupler over the gRPC service for the NMEA2000/CAN data access
#
# Author:      Laurent Carré
#
# Created:     24/05/2025
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import time


from navigation_server.router_common import GrpcClient, ServiceClient, GrpcAccessException, GrpcStreamTimeout
from navigation_server.router_core import NMEA2000Msg

from navigation_server.generated.n2k_can_service_pb2 import CANReadRequest
from navigation_server.generated.n2k_can_service_pb2_grpc import CAN_ControllerServiceStub
from navigation_server.generated.nmea2000_pb2 import nmea2000pb

_logger = logging.getLogger("ShipDataServer." + __name__)


class CANGrpcStreamReader(ServiceClient):
    """
    CANGrpcStreamReader is a specialized client for reading CAN messages over a gRPC interface.

    This class facilitates connecting to a gRPC server to stream CAN messages using
    specified filtering criteria. It initializes a connection, manages streaming operations,
    and provides methods to read and close the stream. The configuration setup includes
    filters for sources and PGNs using inclusion and exclusion rules.

    Attributes:
        _server (str): The hostname or IP address of the gRPC server.
        _port (int): The port number for the gRPC server.
        _select_sources (List[int]): List of source identifiers to filter and include in
            the stream.
        _reject_sources (List[int]): List of source identifiers to filter and exclude from
            the stream.
        _select_pgn (List[int]): List of PGN values to filter and include in the stream.
        _reject_pgn (List[int]): List of PGN values to filter and exclude from the stream.
        _client (GrpcClient): A gRPC client instance used for managing the connection and
            communication.
        _can_request (CANReadRequest): An instance of CANReadRequest containing the filter
            criteria for CAN messages.

    Methods:
        start_stream: Initiates the gRPC connection and starts the message stream.
        read: Reads a single message from the stream while applying filters.
        close: Closes the gRPC stream.
    """
    def __init__(self, reference, kwargs: dict):
        """
        Manages the interaction with the gRPC CAN Controller service by establishing a connection and
        configuring various request parameters.

        This class requires mandatory parameters for server address and port. Optional parameters
        can be specified to refine the behavior of the CAN data requests, such as selecting or rejecting
        sources and parameter group numbers (PGN). Ensures that the client properly configures itself
        for interaction with the CAN Controller service.

        Attributes:
            _server: The server address for the CAN Controller service.
            _port: The port number to connect to the CAN Controller service.
            _select_sources: A list of specific source IDs to include in the CAN requests.
            _reject_sources: A list of specific source IDs to exclude from the CAN requests.
            _select_pgn: A list of specific Parameter Group Numbers (PGN) to include.
            _reject_pgn: A list of specific Parameter Group Numbers (PGN) to exclude.
            _client: The gRPC client used to interact with the CAN Controller service.
            _can_request: The CAN read request object configured for the client.

        Args:
            reference (str): A unique identifier for the client or reference.
            opts: A collection of configuration options including 'source_server', 'source_port',
                'select_sources', 'reject_sources', 'select_pgn', and 'reject_pgn'.

        Raises:
            ValueError: Raised if the 'server' or 'port' parameter is not provided in the options.
        """
        super().__init__(CAN_ControllerServiceStub)
        self._server = kwargs.get('source_server', None)
        if self._server is None:
            _logger.error(f"class {self.__class__.__name__} the 'server' parameter is mandatory")
            raise ValueError
        self._port= kwargs.get('source_port', 0)
        if self._port == 0:
            _logger.error(f"class {self.__class__.__name__} the 'port' parameter is mandatory")
            raise ValueError
        #
        self._select_sources = kwargs.get('select_sources', None)
        self._reject_sources = kwargs.get('reject_sources', None)
        self._select_pgn = kwargs.get('select_pgn', None)
        self._reject_pgn = kwargs.get('reject_pgn', None)
        self._client:GrpcClient = GrpcClient.get_client(f"{self._server}:{self._port}")
        self._client.add_service(self)
        self._can_request = CANReadRequest()
        self._can_request.client = f"{reference}-reader"
        if self._select_sources is not None:
            self._can_request.select_sources.extend(self._select_sources)
        elif self._reject_sources is not None:
            self._can_request.reject_sources.extend(self._reject_sources)
        if self._select_pgn is not None:
            self._can_request.select_pgn.extend(self._select_pgn)
        elif self._reject_pgn is not None:
            self._can_request.reject_pgn.extend(self._reject_pgn)

    def start_stream_to_queue(self):
        _logger.debug("CANGrpcStreamReader start stream to queue")
        if self.server_not_connected:
            _logger.debug("CANGrpcStreamReader start => not connected")
            self.server_connect()
            success = self.server_connect_wait(20.0)
        else:
            success = True
        if success:
            _logger.debug("CANGrpcStreamReader start => connected")
            if not self.stream_is_alive():
                self._start_read_stream_to_queue(self._stub.ReadNmea2000Msg, self._can_request)
            return True
        else:
            _logger.debug("CANGrpcStreamReader start => failed")
            return False

    def start_stream_to_callback(self, process_msg_callback):
        _logger.debug("CANGrpcStreamReader start stream to callback")
        if  self.server_not_connected:
            self.server_connect()
            success = self.server_connect_wait(20.)
        else:
            success = True
        if success:
            _logger.debug("CANGrpcStreamReader start => connected")
            if not self.stream_is_alive():
                self._start_read_stream_to_callback(self._stub.ReadNmea2000Msg, self._can_request, process_msg_callback)
            return True
        else:
            _logger.debug("CANGrpcStreamReader start => failed")
            return False

    def wait_for_stream(self):
        self._wait_for_stream_end()

    def read(self):
        """
        Reads a message from the gRPC stream if the client is connected and in stream to queue mode. Handles
        exceptions for stream reading and reconnects upon facing errors. If the client
        is not connected, it waits before raising an error. Returns an NMEA2000
        message parsed from the protobuf data in case of successful read.

        Raises:
            StreamReadError: Raised if the stream cannot be read due to connection issues.
            StreamTimeOut: Raised if the gRPC stream reading times out.

        Returns:
            NMEA2000Msg: Parsed message containing the PGN and protobuf data.
        """
        if self.server_connected:
            try:
                pb_msg = self._read_stream()
                _logger.debug("N2KGrpcCoupler message received with PGN %d" % pb_msg.pgn)
            except GrpcAccessException:
                # ok, we have a problem, let's wait and restart later
                _logger.debug("N2KGrpcCoupler => GrpcAccessException")
                time.sleep(1.0)
                raise
            except GrpcStreamTimeout:
                _logger.debug("N2KGrpcCoupler => GrpcStreamTimeout")
                raise
            return NMEA2000Msg(pgn=pb_msg.pgn, protobuf=pb_msg)

        else:
            # let's wait
            time.sleep(10.0)
            raise GrpcAccessException

    def close(self):
        self._stop_read_stream()


