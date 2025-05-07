#-------------------------------------------------------------------------------
# Name:        network_service.py
# Purpose:     Implementation of the network service based on NetworkManager
# Author:      Laurent Carré
#
# Created:     19/04/2025
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import yaml
import os.path

_logger = logging.getLogger('ShipDataServer.' + __name__)

from navigation_server.router_common import GrpcService, GrpcServerError, get_global_var
from navigation_server.network.nmcli_interface import NetworkManagerControl, NetworkManagerError

from navigation_server.generated.network_pb2_grpc import NetworkServiceServicer, add_NetworkServiceServicer_to_server
from navigation_server.generated.network_pb2 import (NetInterface, NetConnection, NetworkCommand, NetworkStatus,
                                                    NetworkReply, InterfaceStatus, DeviceType)


(NOT_CONNECTED, LAN_CONTROLLER, WAN_INTERFACE, LAN_INTERFACE) = range(4)

device_type_dict = { 'ethernet': DeviceType.ETHERNET, 'wifi': DeviceType.WIFI, 'cellular': DeviceType.CELLULAR}
connection_type_dict = { NOT_CONNECTED: InterfaceStatus.NOT_CONNECTED, LAN_CONTROLLER: InterfaceStatus.LAN_CONTROLLER,
                         WAN_INTERFACE: InterfaceStatus.WAN_INTERFACE, LAN_INTERFACE: InterfaceStatus.LAN_INTERFACE}

status_dict = { 'auto': WAN_INTERFACE, 'manual': LAN_INTERFACE, 'shared': LAN_CONTROLLER}

class NetworkInterface:

    def __init__(self, name, params):
        self._name = name
        self._params = params
        self._connection = None
        self._state = 'unknown'
        self._network_connection = None
        self._status = NOT_CONNECTED


    @property
    def name(self):
        return self._name

    @property
    def type(self):
        return self._params['type']

    @property
    def default_state(self):
        return self._params['default_state']

    @property
    def default_connection(self):
        return self._params['default_connection']

    @property
    def device(self):
        return self._params['device']

    @property
    def connection(self):
        return self._connection

    @connection.setter
    def connection(self, value):
        self._connection = value

    def set_state(self, state):
        self._state = state

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, value):
        self._state = value

    @property
    def status(self):
        return self._status

    @property
    def network_connection(self):
        return self._network_connection

    @network_connection.setter
    def network_connection(self, value):
        self._network_connection = value

    def get_connection_params(self):
        if self.network_connection is None:
            return
        method = self.network_connection.get_property('ipv4.method')
        self._status = status_dict[method]
        # more to come

class NetworkInterfaceConnection:

    def __init__(self, name, params):
        self._name = name
        self._params = params

    @property
    def name(self):
        return self._name


class NetworkServicerImpl(NetworkServiceServicer):

    def __init__(self, service):
        self._service = service
        self._id = 0

    def get_network_status(self, request, context):
        _logger.debug(f'get_network_status: request={request.cmd} nm_running={self._service.network_manager.nm_running}')
        resp = NetworkStatus()
        resp.id = self._id
        self._id += 1
        resp.nm_running = self._service.network_manager.nm_running
        for iface in self._service.interfaces():
            interface = NetInterface()
            interface.name = iface.name
            interface.type = device_type_dict[iface.type]
            interface.status = connection_type_dict[iface.status]
            if iface.state == 'unavailable':
                interface.device_name = "Not available"
            else:
                interface.device_name = iface.device
            resp.if_list.append(interface)
        return resp

    def set_global_configuration(self, request, context):
        _logger.debug(f'set_global_configuration: request={request}')
        resp = NetworkStatus()
        return resp

    def get_configuration(self, request, context):
        _logger.debug(f'get_configuration: request={request}')
        resp = NetworkReply()
        return resp

    def set_configuration(self, request, context):
        _logger.debug(f'set_configuration: request={request}')
        resp = NetworkReply()
        return resp


class NetworkService(GrpcService):

    def __init__(self, opts):
        super().__init__(opts)
        self._configuration_file = opts.get('configuration', str, 'network_conf.yml')
        self._network_manager = NetworkManagerControl()
        self._servicer = None
        self._configuration = None
        self._interfaces = {}
        self._connections = {}
        self.read_configuration()


    @property
    def network_manager(self):
        return self._network_manager

    def interfaces(self):
        return self._interfaces.values()

    def finalize(self):
        try:
            super().finalize()
        except GrpcServerError:
            return
        _logger.info("Adding service %s to server" % self._name)
        self._servicer = NetworkServicerImpl(self)
        add_NetworkServiceServicer_to_server(self._servicer, self.grpc_server)
        # now we get the current situation from NetworkManager
        try:
            self._network_manager.check_network_manager(wait=True)
        except NetworkManagerError as e:
            _logger.critical(f"NetworkService error: {e}")
            self.stop_service()
            return
        _logger.info("NetworkManager running state: %s" % self._network_manager.nm_running)
        self._network_manager.get_networking_conf()
        self.update_configuration()

    def read_configuration(self):
        try:
            path = get_global_var('settings_path')
        except KeyError:
            _logger.error("Missing settings_path global variable")
            raise ValueError
        conf_file = os.path.join(path, self._configuration_file)
        if not os.path.isfile(conf_file):
            _logger.error("Missing configuration file %s" % conf_file)
            raise ValueError
        with open(conf_file, 'r') as fp:
            try:
                self._configuration = yaml.safe_load(fp)
            except yaml.YAMLError as e:
                _logger.error(f"NetworkService error decoding configuration file {conf_file}: {e}")
                raise ValueError
        # now we need to interpret the configuration

        def object_descr_iter(obj_type):
            impl_obj_list = self._configuration[obj_type]
            if impl_obj_list is None:
                # nothing to iterate
                _logger.info("No %s objects in the settings file" % obj_type)
                return
            for impl_obj in impl_obj_list:
                yield impl_obj

        # get the interfaces
        for impl_obj in object_descr_iter('interfaces'):
            # print(impl_obj)
            for items in impl_obj.items():
                interface = NetworkInterface(items[0], items[1])
            self._interfaces[interface.name] = interface

        # now get all connections
        for impl_obj in object_descr_iter('connections'):
            # print(impl_obj)
            for items in impl_obj.items():
                connection = NetworkInterface(items[0], items[1])
            self._connections[connection.name] = connection

    def update_configuration(self):
        """
        Here we check that what we want is inline with what is available in NetworkManager
        """
        for interface in self._interfaces.values():
            try:
                device = self._network_manager.get_device(interface.device)
            except KeyError:
                _logger.error(f"NetworkService interface {interface.name} device {interface.device} not found")
                interface.set_state('unavailable')
                continue
            if device.connection is None or len(device.connection) == 0:
                _logger.info(f"NetworkService interface {interface.name} device {interface.device} has no connection")
                interface.set_state('disconnected')
                continue
            try:
                interface.network_connection = self._network_manager.get_connection(device.connection)
            except KeyError:
                _logger.error(f"NetworkService interface {interface.name} device {interface.device} connection {device.connection} not found")
                interface.set_state('unavailable')
                continue
            # now we need to understand better
            interface.state = device.state
            interface.get_connection_params()

    def apply_defaults(self):
        for interface in self._interfaces.values():
            if interface.state == "unavailable":
                continue
            device = self._network_manager.get_device(interface.device)
            if device.connection != interface.default_connection:
                _logger.info(f"NetworkService actual connection for interface {interface.name} is {device.connection}")
                # lets delete it
                self._network_manager.delete_connection(device.connection)
            else:
                continue
            # now we need to create the correct connection for the interface
            try:
                connection = self._connections[interface.default_connection]
            except KeyError:
                _logger.error(f"NetworkService interface {interface.name} default connection {interface.default_connection} not found")
                interface.set_state('unavailable')
                continue
            self._network_manager.create_connection(connection.name, interface.device, interface.type, connection.params)








