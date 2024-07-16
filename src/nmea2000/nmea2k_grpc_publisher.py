#-------------------------------------------------------------------------------
# Name:        nmea2k_grpc_publisher
#              Publisher sending NMEA2000 over Grpc
# Author:      Laurent Carré
#
# Created:     14/01/2024
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2024
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import threading
import grpc
import logging

from router_core import ExternalPublisher
from .nmea2k_decode_dispatch import get_n2k_decoded_object, N2KMissingDecodeEncodeException
from router_common import NavGenericMsg, N2K_MSG, N0183_MSG
from .generated_base import NMEA2000DecodedMsg, N2K_DECODED
from .nmea0183_to_nmea2k import NMEA0183ToNMEA2000Converter
from router_core import NMEA0183Msg, NMEA2000Msg, NMEAInvalidFrame


from generated.nmea_messages_pb2 import nmea_msg, server_cmd
from generated.input_server_pb2_grpc import NMEAInputServerStub

_logger = logging.getLogger("ShipDataServer." + __name__)


class GrpcPublisher(ExternalPublisher):

    def __init__(self, opts):
        super().__init__(opts)
        self._decoded_n2k = opts.get('decode_nmea2000', bool, True)
        self._nmea183 = opts.get_choice('nmea0183', ['convert_strict', 'pass_thru', 'convert_pass' ], 'pass_thru')
        if self._nmea183 in ('convert_strict', 'convert_pass'):
            self._converter = NMEA0183ToNMEA2000Converter()
        else:
            self._converter = None
        self._max_retry = opts.get('max_retry', int, 20)
        self._retry_interval = opts.get('retry_interval', float, 10.0)
        self._trace_missing_pgn = opts.get('trace_missing_pgn', bool, False)
        self._stop_on_error = opts.get('stop_on-error', bool, False)
        self._address = "%s:%d" % (opts.get('address', str, '127.0.0.1'), opts.get('port', int, 4502))
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
        if gen_msg.type == N0183_MSG:
            self.process_nmea183(gen_msg)
        elif gen_msg.type == N2K_MSG:
            self.process_n2k_raw(gen_msg.msg)
        elif gen_msg.type == N2K_DECODED:
            self.send_decoded_n2k(gen_msg)
        return True

    def process_n2k_raw(self, n2k_msg: NMEA2000Msg):

        _logger.debug("gRPC publisher N2K input msg %s" % n2k_msg.format2())

        if self._decoded_n2k:
            try:
                decoded_msg = get_n2k_decoded_object(n2k_msg)
                self.send_pb_message(decoded_msg.protobuf_message())
            except N2KMissingDecodeEncodeException:
                if self._trace_missing_pgn:
                    _logger.info("Missing PGN %d decode/encode class" % n2k_msg.pgn)
        else:
            self.send_n2k_raw(n2k_msg)
        return True

    def process_nmea183(self, msg: NavGenericMsg):
        # convert the NMEA0183 messages and send the NMEA2000 messages
        _logger.debug("gRPC Publisher NMEA0183 input: %s" % msg)
        messages = None
        if self._nmea183 in ('convert_strict', 'convert_pass'):
            try:
                for n2k_msg in self._converter.convert(msg):
                    self.send_decoded_n2k(n2k_msg)
            except NMEAInvalidFrame:
                if self._nmea183 != 'convert_strict':
                    self.send_nmea0183(msg.msg)
            except Exception as e:
                _logger.error("NMEA0183 decoding error:%s" % e)
        else:
            # pass_thru case
            self.send_nmea0183(msg.msg)

    def send_decoded_n2k(self, msg: NMEA2000DecodedMsg):
        if self._decoded_n2k:
            self.send_pb_message(msg.protobuf_message())
        else:
            # then we need to reencode
            n2k_msg = msg.message()
            self.send_n2k_raw(n2k_msg)

    def send_nmea0183(self, msg: NMEA0183Msg):
        msgpb = nmea_msg()
        msg.as_protobuf(msgpb.N0183_msg, set_raw=True)
        self.send_message(msgpb)

    def send_n2k_raw(self, msg: NMEA2000Msg):
        msgpb = nmea_msg()
        msg.as_protobuf(msgpb.N2K_msg)
        self.send_message(msgpb)

    def stop(self):
        self._channel.close()
        super().stop()
        if self._timer is not None:
            self._timer.cancel()

    def send_pb_message(self, msg):
        _logger.debug("gRPC Publisher send decoded message: %s" % msg)
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
        _logger.debug("gRPC Publisher send message: %s" % msg)
        try:
            resp = self._stub.pushNMEA(msg)
        except grpc.RpcError as err:
            if err.code() != grpc.StatusCode.UNAVAILABLE:
                _logger.error("Server Status - Error accessing server:%s" % err)
                assert self._stop_on_error
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
            # self._ready = False
        elif connectivity == grpc.ChannelConnectivity.CONNECTING:
            _logger.info("GRPC Channel Connecting")
        elif connectivity == grpc.ChannelConnectivity.SHUTDOWN:
            _logger.info("GRPC Channel Shutdown")



