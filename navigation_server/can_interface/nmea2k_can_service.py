#-------------------------------------------------------------------------------
# Name:        nmea2k_can_service_service.py
# Purpose:     gRPC service for the NMEA2000/CAN data access
#
# Author:      Laurent Carré
#
# Created:     29/04/2025
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import time


from navigation_server.generated.n2k_can_service_pb2 import N2KDeviceMsg, CAN_ControllerMsg, CANRequest
from navigation_server.generated.n2k_can_service_pb2_grpc import CAN_ControllerServiceServicer, add_CAN_ControllerServiceServicer_to_server
from navigation_server.generated.iso_name_pb2 import ISOName
from navigation_server.router_common import GrpcService, get_global_var, resolve_ref
from navigation_server.can_interface import NMEA2KActiveController

_logger = logging.getLogger("ShipDataServer." + __name__)


class CAN_ControllerServiceServicerImpl(CAN_ControllerServiceServicer):

    def __init__(self, controller):
        self._controller: NMEA2KActiveController = controller
        self._start_period = time.monotonic()
        self._start_in_counter = 0
        self._start_out_counter = 0
        _logger.debug("CAN_ControllerServiceServicer created on controller:%s" % self._controller.name)

    def GetStatus(self, request, context):
        _logger.debug("Get NMEA200/ CAN status and devices request")
        resp = CAN_ControllerMsg()
        if self._controller is None:
            _logger.error("No NMEA200 Server present")
            resp.channel = "NO_CAN"
            resp.status = "No CAN interface and controller available"
            return resp
        if request.cmd == 'poll':
            _logger.debug("Poll for devices first")
            self._controller.poll_devices()
            time.sleep(3.0) # wait a bit to get the responses

        resp.channel = self._controller.channel
        in_counter = self._controller.CAN_interface.total_msg_raw()
        out_counter = self._controller.CAN_interface.total_msg_raw_out()
        _logger.debug(
            "CAN_ControllerServiceServicerImpl counters %s %s" % (in_counter, out_counter))
        end_period = time.monotonic()
        resp.incoming_rate = (in_counter - self._start_in_counter) / (end_period - self._start_period)
        resp.outgoing_rate = (out_counter - self._start_out_counter) / (end_period - self._start_period)
        self._start_period = end_period
        self._start_in_counter = in_counter
        self._start_out_counter = out_counter

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
            resp.devices.append(dev_pb)
        _logger.debug("Get NMEA Devices END")
        return resp


class N2KCanService(GrpcService):

    def __init__(self, opts):
        super().__init__(opts)
        self._ctlr_name = opts.get('can_controller', str, None)
        self._nmea2k_ECU = None
        self._servicer = None

    def finalize(self):
        if self._ctlr_name is not None:
            try:
                self._nmea2k_ECU = resolve_ref(self._ctlr_name)
            except KeyError:
                pass
        if self._nmea2k_ECU is None:
            try:
                self._nmea2k_ECU = get_global_var("NMEA2K_ECU")
            except KeyError:
                _logger.critical(f"N2KCanService {self._name} => No Can controller (ECU)")
                return
        super().finalize()
        self._servicer = CAN_ControllerServiceServicerImpl(self._nmea2k_ECU)
        add_CAN_ControllerServiceServicer_to_server(self._servicer, self.grpc_server)
