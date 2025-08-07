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
from navigation_server.network.mmcli_interface import ModemControl

from navigation_server.generated.network_pb2_grpc import NetworkServiceServicer, add_NetworkServiceServicer_to_server
from navigation_server.generated.network_pb2 import (NetInterface, NetConnection, NetworkCommand, NetworkStatus,
                                                    NetworkReply, InterfaceStatus, DeviceType)


(NOT_CONNECTED, LAN_CONTROLLER, WAN_INTERFACE, LAN_INTERFACE) = range(4)

device_type_dict = { 'ethernet': DeviceType.ETHERNET, 'wifi': DeviceType.WIFI, 'cellular': DeviceType.CELLULAR}
connection_type_dict = { NOT_CONNECTED: InterfaceStatus.NOT_CONNECTED, LAN_CONTROLLER: InterfaceStatus.LAN_CONTROLLER,
                         WAN_INTERFACE: InterfaceStatus.WAN_INTERFACE, LAN_INTERFACE: InterfaceStatus.LAN_INTERFACE}

status_dict = { 'auto': WAN_INTERFACE, 'manual': LAN_INTERFACE, 'shared': LAN_CONTROLLER}

class NetworkInterface:

    def __init__(self, name, params: dict):
        self._name = name
        self._params: dict = params
        self._connection = None
        self._state = 'unknown'
        self._network_connection = None
        self._status = NOT_CONNECTED


    @property
    def name(self):
        return self._name

    @property
    def params(self) -> dict:
        return self._params

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

    def set_protobuf(self, pb_interface: NetInterface):
        pb_interface.name = self._name
        pb_interface.type = device_type_dict[self._params['type']]
        pb_interface.status = connection_type_dict[self._status]
        if self._state == 'unavailable':
            pb_interface.device_name = "Not available"
        else:
            pb_interface.device_name = self._params['device']

class NetworkInterfaceConnection:

    def __init__(self, name, params):
        self._name = name
        self._params = params

    @property
    def name(self):
        return self._name


class NetworkServicerImpl(NetworkServiceServicer):

    def __init__(self, service: 'NetworkService'):
        self._service = service
        self._id = 0

    def get_network_status(self, request, context):
        _logger.debug(f'get_network_status: request={request.cmd} nm_running={self._service.network_manager.nm_running}')
        resp = NetworkStatus()
        resp.id = self._id
        self._id += 1
        resp.nm_running = self._service.network_manager.nm_running
        if resp.nm_running:
            if request.cmd == 'update':
                self._service.update_configuration()
            self.fill_network_status(resp)
        return resp

    def set_global_configuration(self, request, context):
        _logger.debug(f'set_global_configuration: request={request}')
        resp = NetworkStatus()
        resp.id = self._id
        self._id += 1
        self._service.apply_defaults()
        self._service.update_configuration()
        self.fill_network_status(resp)
        return resp

    def get_configuration(self, request, context):
        _logger.debug(f'get_configuration: request={request}')
        resp = NetworkReply()
        return resp

    def set_configuration(self, request, context):
        _logger.debug(f'set_configuration: request={request}')
        resp = NetworkReply()
        resp.id = self._id
        self._id += 1
        try:
            interface = self._service.interface(request.interface.name)
        except KeyError:
            _logger.error(f"NetworkService interface {request.interface.name} not found")
            resp.status = "Interface not found"
            return resp
        if request.cmd == 'default':
            self._service.apply_default_connection(interface)
            interface.set_protobuf(resp.interface)



        return resp

    def fill_network_status(self, resp):
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


class NetworkService(GrpcService):

    def __init__(self, opts):
        super().__init__(opts)
        self._configuration_file = opts.get('configuration', str, 'network_conf.yml')
        self._network_manager = NetworkManagerControl()
        self._modem_manager = ModemControl()
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

    def interface(self, name):
        return self._interfaces[name]

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
        if self._interfaces.get('cellular', None) is not None:
            if not self._modem_manager.detect():
                # ok the modem is not yet showing up
                _logger.info("No modem detected yet => starting power-on sequence")
                self._modem_manager.power_on_sequence(self.modem_update)
        self.update_configuration()
        # let's see if we have to manage a modem


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
            keys = list(impl_obj)
            name = keys[0]
            params = impl_obj[name]
            # print(params)
            if type(params) is not dict:
                raise ValueError("Invalid interface configuration")
            interface = NetworkInterface(name, params)
            self._interfaces[interface.name] = interface

        # now get all connections
        for impl_obj in object_descr_iter('connections'):
            # print(impl_obj)
            keys = list(impl_obj)
            name = keys[0]
            params = impl_obj[name]
            # print(params)
            if type(params) is not dict:
                raise ValueError("Invalid interface configuration")
            connection = NetworkInterface(name, params)
            self._connections[connection.name] = connection

    def update_configuration(self):
        """
        Here we check that what we want is inline with what is available in NetworkManager
        """
        for interface in self._interfaces.values():
            self.update_interface(interface)

    def modem_update(self):
        interface = self._interfaces.get('cellular', None)
        if interface is not None:
            try:
                self._network_manager.read_device_configuration(interface.device, 'gsm')
            except NetworkManagerError as e:
                _logger.error(f"NetworkService error reading modem device configuration: {e}")
                return
            except ValueError as e:
                _logger.error(f"NetworkService error reading modem device configuration: {e}")
                return
            self.update_interface(interface)

    def update_interface(self, interface: NetworkInterface):
        try:
            device = self._network_manager.get_device(interface.device)
        except KeyError:
            _logger.error(f"NetworkService interface {interface.name} device {interface.device} not found")
            interface.set_state('unavailable')
            return
        if device.connection is None or len(device.connection) == 0:
            _logger.info(f"NetworkService interface {interface.name} device {interface.device} has no connection")
            interface.set_state('disconnected')
            return
        try:
            interface.network_connection = self._network_manager.get_connection(device.connection)
        except KeyError:
            _logger.error(
                f"NetworkService interface {interface.name} device {interface.device} connection {device.connection} not found")
            interface.set_state('unavailable')
            return
        # now we need to understand better
        interface.state = device.state
        interface.get_connection_params()

    def apply_defaults(self):
        for interface in self._interfaces.values():
            self.apply_default_connection(interface)


    def apply_default_connection(self, interface: NetworkInterface):
        _logger.debug(f"NetworkService applying default connection for interface {interface.name} device {interface.device} default connection {interface.default_connection}")
        if interface.state == "unmanaged":
            _logger.info(f"NetworkService interface {interface.name} device {interface.device} is unmanaged")
            return
        device = self._network_manager.get_device(interface.device)
        if device.connection != interface.default_connection:
            _logger.info(f"NetworkService actual connection for interface {interface.name} is {device.connection}")
            # lets delete it
            self._network_manager.delete_connection(device.connection)
        else:
            _logger.info(f"NetworkService interface {interface.name} device {interface.device} default connection {device.connection} already set")
            return
        # now we need to create the correct connection for the interface
        try:
            connection = self._connections[interface.default_connection]
        except KeyError:
            _logger.error(
                f"NetworkService interface {interface.name} default connection {interface.default_connection} not found")
            interface.set_state('unavailable')
            return
        _logger.info(
            f"NetworkService creating connection {connection.name} for interface {interface.name} device {interface.device} with:{connection.params}")
        self._network_manager.create_connection(connection.name, interface.device, interface.type, connection.params)
        self.update_interface(interface)




