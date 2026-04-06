#-------------------------------------------------------------------------------
# Name:        nmea2k_can_service_service.py
# Purpose:     gRPC service for the NMEA2000/CAN data access
#
# Author:      Laurent Carré
#
# Created:     29/04/2025
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2026
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import time


<<<<<<<< HEAD:navigation_server/nmea2000/nmea2k_service.py
from navigation_server.generated.nmea2000_service_pb2 import (N2KDeviceMsg, Nmea2000ControllerMsg, Nmea2000Request, Nmea2000ReadRequest,
                                                             Nmea2000Ack, PGN_statistic)
from navigation_server.generated.nmea2000_service_pb2_grpc import Nmea2000ControllerServiceServicer, add_Nmea2000ControllerServiceServicer_to_server
========
from navigation_server.generated.n2k_can_service_pb2 import (N2KDeviceMsg, CAN_ControllerMsg, CANRequest, CANReadRequest,
                                                             CANAck, PGN_statistic)
from navigation_server.generated.n2k_can_service_pb2_grpc import CAN_ControllerServiceServicer, add_CAN_ControllerServiceServicer_to_server
>>>>>>>> ac15aad (V2.8.0 release):navigation_server/can_interface/nmea2k_can_service.py
from navigation_server.generated.nmea2000_pb2 import nmea2000pb
from navigation_server.generated.iso_name_pb2 import ISOName
from navigation_server.generated.nmea_messages_pb2 import server_resp
from navigation_server.router_common import GrpcService, get_global_var, resolve_ref, MessageTraceError
from navigation_server.router_core import NMEA2000Msg
from navigation_server.nmea2000 import NMEA2KController

_logger = logging.getLogger("ShipDataServer." + __name__)


class Nmea2000ControllerServiceServicerImpl(Nmea2000ControllerServiceServicer):

    def __init__(self, controller):
        self._controller: NMEA2KController = controller
        self._start_period = time.monotonic()
        self._start_in_counter = 0
        self._start_out_counter = 0
        _logger.debug("Nmea2000ControllerServiceServicer created on controller:%s" % self._controller.name)

    def GetStatus(self, request, context):
        _logger.debug("Get NMEA200 status and devices request")
        resp = Nmea2000ControllerMsg()
        if self._controller is None:
            _logger.error("No NMEA200 Server present")
            resp.channel = "NO_NMEA2000"
            resp.status = "No CAN interface and controller available"
            return resp
        if request.cmd == 'poll':
            _logger.debug("Poll for devices first")
            self._controller.poll_devices()
            time.sleep(3.0) # wait a bit to get the responses

        resp.channel = self._controller.channel
        in_counter = self._controller.total_msg_raw()
        out_counter = self._controller.total_msg_raw_out()
        _logger.debug(
            "Nmea2000ControllerServiceServicerImpl counters %d %d" % (in_counter, out_counter))
        end_period = time.monotonic()
        resp.incoming_rate = (in_counter - self._start_in_counter) / (end_period - self._start_period)
        resp.outgoing_rate = (out_counter - self._start_out_counter) / (end_period - self._start_period)
        self._start_period = end_period
        self._start_in_counter = in_counter
        self._start_out_counter = out_counter

        resp.traces_on = self._controller.is_trace_active()

        for device in self._controller.get_device():
            dev_pb = N2KDeviceMsg()
            dev_pb.address = device.address
            dev_pb.changed = device.changed()
            device.clear_change_flag()
            _logger.debug("Console sending NMEA2000 Device address %d info" % device.address)
            if device.iso_name is not None:
                device.iso_name.set_protobuf(dev_pb.iso_name)
                dev_pb.iso_name.manufacturer_name = device.manufacturer_name
            else:
                _logger.debug("Device address %d partial info only" % device.address)
            dev_pb.last_time_seen = device.last_time_seen
            if device.product_information is not None:
                device.product_information.set_protobuf(dev_pb.product_information)
            if device.configuration_information is not None:
                device.configuration_information.set_protobuf(dev_pb.configuration_information)
            # now add the statistics on PGN
            for stat_pgn in device.pgn_received():
                stat_pb = PGN_statistic()
                stat_pb.pgn = stat_pgn[0]
                stat_pb.count = stat_pgn[1]
                dev_pb.stats.append(stat_pb)
            resp.devices.append(dev_pb)
        _logger.debug("Get NMEA Devices END")
        return resp

    def StartTrace(self, request, context):
        _logger.debug("NMEA2000 Service Start trace")
        resp = Nmea2000ControllerMsg()
        resp.channel = self._controller.channel
        if self._controller.is_trace_active():
            resp.status = f"trace already running on channel {resp.channel}"
            resp.traces_on = True
        else:
            try:
                self._controller.start_trace(request.cmd)
                resp.status = f"trace started on channel {resp.channel}"
                resp.traces_on = True
            except MessageTraceError:
                resp.status = f"trace star error on channel {resp.channel}"
                resp.traces_on = False
        return resp

    def StopTrace(self, request, context):
        _logger.debug("NMEA2000 Service stop trace")
        resp = Nmea2000ControllerMsg()
        resp.channel = self._controller.channel
        self._controller.stop_trace()
        resp.traces_on = False
        return resp

    def ReadNmea2000Msg(self, request: Nmea2000ReadRequest, context):
        """
        Start a reading stream of NMEA2000 messages
        """
        _logger.debug("NMEA CAN service -> ReadNmea2000Msg from %s" % context.peer())
        stream_id = f"{request.client}-{context.peer()}"
        msg_stream = self._controller.add_read_subscriber(stream_id,
                                                          request.select_sources,
                                                          request.reject_sources,
                                                          request.select_pgn,
                                                          request.reject_pgn,
                                                          timeout=60.)
        while True:
            msg = msg_stream.get_message()
            msg_pb = nmea2000pb()
            msg.as_protobuf(msg_pb)
            _logger.debug("ReadNmea2000 => Pushing message with PGN %d" % msg_pb.pgn)
            yield msg_pb

    def SendNmea2000Msg(self, request, context):
        """
        Send a NMEA2000 message to the CAN directly or indirectly via adapters
        The request includes the sending device and the message
        When going through adapters, the device cannot be controlled
        """
        _logger.debug("NMEA2000 service -> SendNmea2000Msg to %s PGN %d" % (request.device, request.n2k_msg.pgn))
        resp = Nmea2000Ack()
        resp.id = request.id
        resp.messages_count = 1
        n2k_msg = NMEA2000Msg(pgn=request.n2k_msg.pgn, protobuf=request.n2k_msg)
        try:
            resp.error = self._controller.send_message_from_application(request.device, n2k_msg)
        except Exception as e:
            _logger.error(f"SendNmea2000Msg processing error: {e}")
            resp.error = 101
        return resp

    def SendNmea2000Stream(self, request_iterator, context):
        _logger.debug("NMEA2000 service -> SendNmea2000Stream from %s" % context.peer())
        resp = server_resp()
        try:
            for msg in request_iterator:
                n2k_msg = NMEA2000Msg(pgn=msg.pgn, protobuf=msg)
                self._controller.send_message(n2k_msg)
        except Exception as err:
            _logger.error(f"SendNmea2000Stream processing error:{err}")
            resp.reportCode = 101
            resp.status = str(err)
        else:
            _logger.info("SendNmea2000Stream processing stream ends")
            resp.reportCode = 0
        return resp


class Nmea2000Service(GrpcService):

    def __init__(self, opts):
        super().__init__(opts)
        self._ctlr_name = opts.get('nmea2000_controller', str, None)
        self._controller = None
        self._servicer = None

    def finalize(self):
        if self._ctlr_name is not None:
            try:
                self._controller = resolve_ref(self._ctlr_name)
            except KeyError:
                pass
        if self._controller is None:
            try:
                self._controller = get_global_var("NMEA2K_ECU")
            except KeyError:
                _logger.critical(f"NMEA2000Service {self._name} => No NMEA2000 controller")
                return
        super().finalize()
        self._servicer = Nmea2000ControllerServiceServicerImpl(self._controller)
        add_Nmea2000ControllerServiceServicer_to_server(self._servicer, self.grpc_server)
        _logger.debug("N2KCanService %s ready" % self.name)
