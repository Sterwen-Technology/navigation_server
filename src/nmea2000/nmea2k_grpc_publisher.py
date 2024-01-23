#-------------------------------------------------------------------------------
# Name:        nmea2k_grpc_publisher
#              Publisher sending NMEA2000 over Grpc
# Author:      Laurent Carré
#
# Created:     14/01/2024
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2024
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import threading
import grpc
from nmea_routing.publisher import Publisher
from nmea_routing.filters import FilterSet
from nmea2000.nmea2k_decode_dispatch import get_n2k_decoded_object, N2KMissingDecodeEncodeException
from nmea_routing.generic_msg import *
from nmea2000.generated_base import NMEA2000DecodedMsg
from nmea0183.nmea0183_to_nmea2k import default_converter, Nmea0183InvalidMessage

from generated.nmea_messages_pb2 import nmea_msg, server_cmd
from generated.input_server_pb2_grpc import NMEAInputServerStub

_logger = logging.getLogger("ShipDataServer." + __name__)


class N2KGrpcPublisher(Publisher):

    def __init__(self, opts):
        super().__init__(opts)
        filter_names = opts.getlist('filters', str)
        self._protobuf = opts.get('protobuf', bool, True)
        self._convert_nmea183 = opts.get('convert_nmea0183', bool, False)
        self._max_retry = opts.get('max_retry', int, 20)
        self._retry_interval = opts.get('retry_interval', float, 10.0)
        self._trace_missing_pgn = opts.get('trace_missing_pgn', bool, False)
        if filter_names is not None and len(filter_names) > 0:
            _logger.info("Publisher:%s filter set:%s" % (self.object_name(), filter_names))
            self._filters = FilterSet(filter_names)
            self._filter_select = True
        self._address = "%s:%d" % (opts.get('address', str, '127.0.0.1'), opts.get('port', int, 4504))
        _logger.info("Creating client for data server at %s" % self._address)
        self._channel = grpc.insecure_channel(self._address)
        self._channel.subscribe(self.channel_callback)
        self._stub = NMEAInputServerStub(self._channel)
        self._ready = True
        self._timer = None
        self._nb_retry = 0

    def process_msg(self, gen_msg):
        if not self._ready:
            return True
        if gen_msg.type != N2K_MSG:
            if self._convert_nmea183:
                self.process_nmea183(gen_msg)
                return True
            else:
                return True
        n2k_msg = gen_msg.msg
        _logger.debug("Trace publisher N2K input msg %s" % n2k_msg.format2())

        # print("decoding %s", msg.format1())
        if self._protobuf:
            try:
                decoded_msg = get_n2k_decoded_object(n2k_msg)
                self.send_pb_message(decoded_msg.protobuf_message())
            except N2KMissingDecodeEncodeException:
                if self._trace_missing_pgn:
                    _logger.info("Missing PGN %d decode/encode class" % n2k_msg.pgn)
        else:
            msg = n2k_msg.protobuf_message()
            self.send_message(msg)

        return True

    def process_nmea183(self, msg: NavGenericMsg):
        # convert the NMEA0183 messages and send the NMEA2000 messages
        _logger.debug("Grpc Publisher NMEA0183 input: %s" % msg)
        try:
            messages = default_converter.convert(msg)
        except Nmea0183InvalidMessage:
            return
        except Exception as e:
            _logger.error("NMEA0183 decing error:%s" % e)
            return

        if messages is not None:
            for msg in messages:
                if self._protobuf:
                    self.send_pb_message(msg.protobuf_message())
                else:
                    n2k_msg = msg.message()
                    self.send_message(n2k_msg.protobuf_message())

    def stop(self):
        self._channel.close()
        super().stop()
        if self._timer is not None:
            self._timer.cancel()

    def send_pb_message(self, msg):
        try:
            resp = self._stub.pushDecodedNMEA2K(msg)
        except grpc.RpcError as err:
            if err.code() != grpc.StatusCode.UNAVAILABLE:
                _logger.error("Server Status - Error accessing server:%s" % err)
            else:
                _logger.error("Data client %s GRPC Server %s not accessible" % (self._name, self._address))
            self._ready = False
            # let's wait a bit
            self._timer = threading.Timer(10.0, self.retry_timer)
            self._timer.start()
            return

        if resp.reportCode != 0:
            _logger.error("Grpc Publisher error returned by server %s" % resp.status)

    def send_message(self, msg):
        try:
            resp = self._stub.pushNMEA(msg)
        except grpc.RpcError as err:
            if err.code() != grpc.StatusCode.UNAVAILABLE:
                _logger.error("Server Status - Error accessing server:%s" % err)
            else:
                _logger.error("Data client %s GRPC Server %s not accessible" % (self._name, self._address))
                self._ready = False
                # let's wait a bit
                self._timer = threading.Timer(self._retry_interval, self.retry_timer)
                self._timer.start()
            return

        if resp.reportCode != 0:
            _logger.error("Grpc Publisher error returned by server %s" % resp.status)

    def check_status(self) -> bool:
        msg = server_cmd()
        msg.cmd = "TEST_STATUS"
        try:
            resp = self._stub.status(msg)
        except grpc.RpcError as err:
            if err.code() != grpc.StatusCode.UNAVAILABLE:
                _logger.error("Server Status - Error accessing server:%s" % err)
            else:
                _logger.error("Data client %s GRPC Server %s not accessible" % (self._name, self._address))
            return False
        if resp.status == "SERVER_OK":
            return True
        else:
            return False

    def retry_timer(self):
        self._timer = None
        _logger.debug("Retry timer for Grpc connection")
        # check first
        if self.check_status():
            if not self._ready:
                _logger.info("Data client %s => GRPC server %s back on line" % (self._name, self._address))
            self._ready = True
            self._nb_retry = 0
        else:
            self._nb_retry += 1
            if (
                    0 < self._max_retry < self._nb_retry):
                _logger.error("Server at address %s not reachable => stopping published %s" % (self._address,
                                                                                               self.object_name()))
                self.stop()
            else:
                self._timer = threading.Timer(self._retry_interval, self.retry_timer)
                self._timer.start()

    def channel_callback(self, connectivity: grpc.ChannelConnectivity):
        if connectivity == grpc.ChannelConnectivity.READY:
            _logger.info("GRPC Channel Ready")
            self._ready = True
        elif connectivity == grpc.ChannelConnectivity.IDLE:
            _logger.info("GRPC Channel IDLE")
            self._ready = False
        elif connectivity == grpc.ChannelConnectivity.CONNECTING:
            _logger.info("GRPC Channel Connecting")
        elif connectivity == grpc.ChannelConnectivity.SHUTDOWN:
            _logger.info("GRPC Channel Shutdown")



