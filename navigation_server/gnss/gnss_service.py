#-------------------------------------------------------------------------------
# Name:        gnss_service
# Purpose:     implementation of GNSS NMEA0183 GNSS interface - some features are specific to Ublox
#
# Author:      Laurent Carré
#
# Created:     12/04/2025
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import time

import serial
import queue

from navigation_server.router_core import NMEA0183Msg, NMEAInvalidFrame
from navigation_server.router_common import NavThread, NMEAMsgTrace
from navigation_server.gnss.gnss_data import GNSSDataManager, N2KForwarder
from navigation_server.generated.gnss_pb2 import SatellitesInView, ConstellationStatus, GNSS_Status
from navigation_server.generated.gnss_pb2_grpc import GNSSServiceServicer, add_GNSSServiceServicer_to_server, GNSS_InputStub
from navigation_server.router_common import GrpcService, GrpcServerError, GrpcClient, ServiceClient, GrpcAccessException
from navigation_server.generated.nmea2000_pb2 import nmea2000pb

_logger = logging.getLogger("ShipDataServer."+__name__)

gnss_data = GNSSDataManager()


class N0183Subscriber:

    def __init__(self, formatters: list, push_queue: queue.Queue):
        _logger.debug("GNSS Creating NMEA0183 Subscriber with formatters:%s" % formatters)
        self._formatters = formatters
        self._queue = push_queue

    def push(self, msg: NMEA0183Msg):
        if msg.formatter() in self._formatters:
            try:
                _logger.debug("NMEA0183 Subscriber push:%s" % msg)
                self._queue.put(msg, block=True, timeout=0.2)
            except queue.Full:
                _logger.error("GNSS NMEA0183 subscriber queue full discarding message")

class GNSSSerialReader(NavThread):

    def __init__(self, name, fp, trace):
        super().__init__(name, daemon=True)
        self._fp = fp
        self._stop_flag = False
        self._n0183_subscriber = None
        self._n2k_subscriber = N2KForwarder(set(), None)
        self._n2k_decoded_subscriber = None
        if trace:
            self._trace = NMEAMsgTrace(name, "GNSS")
        else:
            self._trace = None

    def nrun(self) -> None:
        while not self._stop_flag:
            try:
                frame = self._fp.readline()
                # print(frame)
            except serial.serialutil.SerialException as err:
                _logger.error(f"GNSS read error {err}")
                break
            if len(frame) == 0:
                # time out
                continue
            if frame[0] != ord('$'):
                _logger.debug("Invalid GNSS frame:%s" % frame)
                continue
            # _logger.debug("GNSS:%s" % frame.removesuffix(b'\r\n'))
            formatter = frame[3:6]
            talker = frame[1:3]
            if talker not in (b'GN', b'GP', b'GA'):
                # temporary => limit the talkers to the one that really matters
                # shall be configurable in the future
                continue
            try:
                msg = NMEA0183Msg(frame)
            except NMEAInvalidFrame:
                continue
            if self._trace is not None:
                self._trace.trace(NMEAMsgTrace.TRACE_IN, msg)
            if self._n0183_subscriber is not None:
                self._n0183_subscriber.push(msg)
            gnss_data.process_nmea0183(msg, self._n2k_subscriber)
        self._trace.stop_trace()

    def set_n2k_subscriber(self, n2k_subscriber: N2KForwarder):
        self._n2k_subscriber = n2k_subscriber

    def set_n0183_subscriber(self, subscriber: N0183Subscriber):
        self._n0183_subscriber = subscriber

    def clear_n0183_subscriber(self):
        self._n0183_subscriber = None

    def stop(self):
        self._stop_flag = True

    def process_gnss(self, msg):
        gnss_data.process_nmea0183(msg)


class GNSSServiceServicerImpl(GNSSServiceServicer):

    def __init__(self):
        pass

    def gnss_status(self, request, context):
        """
        return GNSS status and all data
        several format are possible depending on the request
        """
        return gnss_data.get_status(request.cmd)



class GNSSService(GrpcService):
    """
    This class controls the implementation of both the internal access to the GNSS Chip
    And the external gRPC service
    """
    def __init__(self, opts):
        super().__init__(opts)
        self._device = opts.get('device', str, '/dev/ttyUSB0')
        self._baudrate = opts.get('baudrate', int, 38400)
        self._servicer = None
        self._fp = None
        self._reader = None
        self._pusher = None
        self._push_address = opts.get('address', str, '127.0.0.1')
        self._push_port = opts.get('port', int, 4502)
        self._push = opts.get('push_to_server', bool, False)
        self._push_server = GrpcClient(f"{self._push_address}:{self._push_port}", use_request_id=False)
        self._trace = opts.get('trace', bool, False)


    def finalize(self):
        if self._open_gnss():
            try:
                super().finalize()
            except GrpcServerError:
                return
            _logger.info("Adding service %s to server" % self._name)
            self._servicer = GNSSServiceServicerImpl()
            add_GNSSServiceServicer_to_server(self._servicer, self.grpc_server)
            self._reader = GNSSSerialReader(f"{self._name}:reader", self._fp, self._trace)
            self._reader.start()
            if self._push:
                self._pusher = GNSSPushClient(self._reader, self._push_server)
                self._pusher.start()
        else:
            _logger.error("GNSS Service cannot open device -> service will not start")

    def _open_gnss(self) -> bool:
        """
        Open the link and start the reading flow
        """
        _logger.debug("Opening GNSS port %s" % self._device)
        try:
            self._fp = serial.Serial(self._device, self._baudrate, timeout=5.0)
        except serial.serialutil.SerialException as err:
            _logger.error(f"Error opening GNSS port {self._device}: {err}")
            return False
        return True

    def stop_service(self):
        if self._pusher is not None:
            self._pusher.stop()
        if self._reader is not None:
            self._reader.stop()
            self._reader.join()
            self._reader = None
        if self._fp is not None:
            self._fp.close()
            self._fp = None
        super().stop_service()

    def add_n0183_subscriber(self, subscriber):
        self._reader.set_n0183_subscriber(subscriber)

    def clear_n0183_subscriber(self):
        self._reader.clear_n0183_subscriber()


class GNSSPushClient(ServiceClient, NavThread):
    """
    This class and thread wait input from the reader and push the message towards gRPC
    """
    def __init__(self, reader, server):
        super().__init__(GNSS_InputStub)
        NavThread.__init__(self,name="GNSSPushClient", daemon=True)
        self._input_queue = queue.Queue(20)
        self._reader = reader
        self._server = server
        self._forwarder = N2KForwarder({129025, 129026, 129029}, self._input_queue)
        self._stop_flag = False

    def start(self):
        self._server.add_service(self)
        self._reader.set_n2k_subscriber(self._forwarder)
        self._server.connect()
        super().start()

    def nrun(self) -> None:

        grpc_connected = True
        time_disconnect = 0.0
        while not self._stop_flag:
            # get the message from reader
            try:
                msg = self._input_queue.get(block=True, timeout=1.0)
            except queue.Empty:
                if grpc_connected:
                    continue
            _logger.debug("GNSSPushClient connected %s input_queue:%d" % (grpc_connected, msg.pgn))
            if grpc_connected:
                # we are connected or want to try the connection
                # convert to protobuf
                pb_msg = nmea2000pb()
                msg.as_protobuf(pb_msg)
                try:
                    resp = self._server_call(self._stub.gnss_message, pb_msg, None)
                except GrpcAccessException:
                    self._forwarder.suspend()
                    grpc_connected = False
                    time_disconnect = time.time()
                    continue
            else:
                t = time.time()
                if t - time_disconnect > 10.0:
                    _logger.debug("GNSSPushClient reconnecting")
                    self._server.connect()
                    self._forwarder.resume()
                    grpc_connected = True
                    time_disconnect = t


    def stop(self):
        self._stop_flag = True




