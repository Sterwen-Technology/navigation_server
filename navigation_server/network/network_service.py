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
from collections import namedtuple

_logger = logging.getLogger('ShipDataServer.' + __name__)

from navigation_server.router_common import GrpcService, GrpcServerError, get_global_var, fill_uuid_protobuf
from navigation_server.network.nmcli_interface import NetworkManagerControl, NetworkManagerError
from navigation_server.network.mmcli_interface import ModemControl

from navigation_server.generated.network_pb2_grpc import NetworkServiceServicer, add_NetworkServiceServicer_to_server
from navigation_server.generated.network_pb2 import (NetInterface, NetConnection, NetworkCommand, NetworkStatus,
                                                    NetworkReply, InterfaceFunction, DeviceType, NetParameter,
                                                    NetConnectionDef, NetworkConfigurationReply)


(NOT_CONNECTED, LAN_CONTROLLER, WAN_INTERFACE, LAN_INTERFACE) = range(4)

device_type_dict = { 'ethernet': DeviceType.ETHERNET, 'wifi': DeviceType.WIFI, 'cellular': DeviceType.CELLULAR}
connection_type_dict = { NOT_CONNECTED: InterfaceFunction.NOT_CONNECTED, LAN_CONTROLLER: InterfaceFunction.LAN_CONTROLLER,
                         WAN_INTERFACE: InterfaceFunction.WAN_INTERFACE, LAN_INTERFACE: InterfaceFunction.LAN_INTERFACE}

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
        if self._connection is None:
            return NOT_CONNECTED
        else:
            return self._connection.function

    @property
    def network_connection(self):
        return self._network_connection

    @network_connection.setter
    def network_connection(self, value):
        self._network_connection = value

    @connection.setter
    def connection(self, value):
        self._connection = value
        self._connection.network_connection = self._network_connection
        # now lets get

    def set_protobuf(self, pb_interface: NetInterface):
        pb_interface.name = self._name
        pb_interface.type = device_type_dict[self.type]
        pb_interface.state = self._state

        if self._state == 'unavailable':
            pb_interface.device_name = "Not available"
        else:
            pb_interface.device_name = self._params['device']
        if self._connection is not None:
            pb_interface.function = connection_type_dict[self._connection.function]
            pb_interface.conn.name = self._connection.name
            fill_uuid_protobuf( pb_interface.conn.uuid, self._network_connection.uuid)
            for key, value in self._network_connection.get_properties():
                parameter = NetParameter()
                parameter.name = key
                parameter.value = value
                pb_interface.conn.parameters.append(parameter)
        else:
            pb_interface.function = InterfaceFunction.NOT_CONNECTED

        # _logger.debug(f"NetworkInterface set_protobuf: pb_interface={pb_interface}")

    def __repr__(self):
        pb_version = NetInterface()
        self.set_protobuf(pb_version)
        return f"{pb_version}"


class NetworkInterfaceConnection:

    _functions = {
        "LAN_CONTROLLER": LAN_CONTROLLER,
        "WAN_INTERFACE": WAN_INTERFACE,
        "LAN_INTERFACE": LAN_INTERFACE,
        "none": NOT_CONNECTED
    }

    def __init__(self, name, params):
        self._name = name
        self._params = params
        self._type = params['type']
        self._network_connection = None
        try:
            self._function = self._functions[params['function']]
        except KeyError:
            raise ValueError(f"Invalid or missing connection function for connection:{name}")

    @property
    def name(self):
        return self._name

    @property
    def params(self):
        return self._params

    @property
    def type(self):
        return self._type

    @property
    def network_connection(self):
        return self._network_connection

    @network_connection.setter
    def network_connection(self, value):
        self._network_connection = value

    @property
    def function(self):
        return self._function

    @property
    def uuid(self):
        if self._network_connection is not None:
            return self._network_connection.uuid
        else:
            raise ValueError(f"NetworkInterface connection {self._name} is missing network connection")

    def get_properties(self):
        if self._network_connection is not None:
            for key, value in self._network_connection.get_properties():
                yield key, value
        else:
            raise ValueError(f"NetworkInterface connection {self._name} is missing network connection")





InterfaceConfiguration = namedtuple('InterfaceConfiguration', ['interface', 'connection'])

class NetworkConfiguration:

    def __init__(self, service,  name: str, if_configurations: dict):
        self._name: str = name
        self.params: dict = if_configurations
        self._configurations = {}
        for interface_name, connection_name in if_configurations.items():
            try:
                interface = service.interface(interface_name)
            except KeyError:
                raise ValueError(f"NetworkConfiguration interface {interface_name} not found")
            try:
                connection = service.connection(connection_name)
            except KeyError:
                raise ValueError(f"NetworkConfiguration connection {connection_name} not found")
            if connection.type != interface.type:
                raise ValueError(f"NetworkConfiguration interface {interface_name} connection {connection_name} type mismatch")
            self._configurations[interface_name] = InterfaceConfiguration(interface, connection)

    def connection_for_interface(self, interface: str) -> NetworkInterfaceConnection:
        return self._configurations[interface].connection

    def all_connections(self):
        for interface_conf in self._configurations.values():
            yield interface_conf.interface, interface_conf.connection


class NetworkServicerImpl(NetworkServiceServicer):

    def __init__(self, service: 'NetworkService'):
        self._service = service
        self._id = 0
        self._cmd_vector = {
            "del_connection": self._service.del_connection,
            "up_connection": self._service.up_connection,
            "down_connection": self._service.down_connection
        }

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
        try:
            self._service.apply_configuration(request.cmd)
            self._service.update_configuration()
            self.fill_network_status(resp)
            resp.status = "OK"
            resp.details = "Global configuration applied"
        except NetworkManagerError as e:
            resp.status = f"NetworkManager error: {e.returncode}"
            resp.details = e.message
        return resp

    def get_configuration(self, request, context):
        _logger.debug(f'get_configuration: request={request}')
        resp = NetworkReply()
        resp.id = self._id
        self._id += 1
        resp.status = "Not implemented"
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
            resp.status = "Error in request"
            resp.details = f"Interface {request.interface.name} not found"
            return resp

        if request.cmd == 'configuration':
            try:
                connection = self._service.connection_in_configuration(request.source, interface)
            except KeyError:
                _logger.error(f"NetworkService interface {request.interface.name} default connection not found")
                resp.status= "Error in configuration"
                resp.details = f"NetworkService interface {request.interface.name} default connection not found"
                return resp
        elif request.cmd == 'connection':
            try:
                connection = self._service.connection(request.source)
                if connection.type != interface.type:
                    _logger.error(f"NetworkService interface {request.interface.name} connection {request.connection.name} type mismatch")
                    resp.status = "Connection type mismatch"
                    resp.details = f"Connection {request.connection.name} type mismatch"
                    return resp
            except KeyError:
                _logger.error(f"NetworkService interface {request.interface.name} connection {request.connection.name} not found")
                resp.status = "Error in request"
                resp.details = f"Connection {request.connection.name} not found"
                return resp
        else:
            resp.status = "Command not recognized"
            resp.details = f"network command {request.cmd} unknown"
            return resp

        try:
            resp.details = self._service.apply_connection(interface, connection)
            interface.set_protobuf(resp.interface)
            resp.status = "OK"
        except (ValueError, KeyError):
            _logger.error(f"NetworkService error applying connection for interface {request.interface.name}")
            resp.status = f"Error applying connection"
            resp.details = "Internal error"
        except NetworkManagerError as e:
            resp.status = f"NetworkManager error: {e.returncode}"
            resp.details = e.message
        return resp

    def interface_command(self, request, context):
        _logger.debug(f'interface command {request.cmd} on {request.interface.name}')
        resp = NetworkReply()
        resp.id = self._id
        self._id += 1
        try:
            interface = self._service.interface(request.interface.name)
        except KeyError:
            _logger.error(f"NetworkService interface {request.interface.name} not found")
            resp.status = "Error in request"
            resp.details = f"Interface {request.interface.name} not found"
            return resp

        if request.cmd not in self._cmd_vector.keys():
            resp.status = "Command not recognized"
            resp.details = f"network command {request.cmd} unknown"
            return resp

        try:
            resp.details = self._cmd_vector[request.cmd](interface)
        except NetworkManagerError as err:
            resp.status = f"NetworkManager error: {err.returncode}"
            resp.details = err.message
            return resp
        # now update the configuration for response
        interface.set_protobuf(resp.interface)
        resp.status = "OK"
        return resp

    def get_configuration_base(self, request, context):
        _logger.debug(f"get_configuration_base command:{request.cmd}")
        resp = NetworkConfigurationReply()
        resp.id = self._id
        self._id += 1
        if request.cmd == 'global':
            for config_name in self._service.configuration_names():
                resp.global_configurations.append(config_name)
            resp.status = "OK"
        else:
            resp.status = "Not implemented"
        return resp

    def fill_network_status(self, resp):
        for iface in self._service.interfaces():
            interface = NetInterface()
            iface.set_protobuf(interface)
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
        self._configurations = {}
        self.read_configuration()


    @property
    def network_manager(self):
        return self._network_manager

    def interfaces(self):
        return self._interfaces.values()

    def interface(self, name):
        return self._interfaces[name]

    def connection(self, name):
        return self._connections[name]

    def configuration_names(self):
        return self._configurations.keys()

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
                raise ValueError("Invalid connection configuration")
            connection = NetworkInterfaceConnection(name, params)
            self._connections[connection.name] = connection

        # the configurations
        for impl_obj in object_descr_iter('configurations'):
            # print(impl_obj)
            keys = list(impl_obj)
            name = keys[0]
            params = impl_obj[name]
            # print(params)
            if type(params) is not dict:
                raise ValueError("Invalid configuration definition")
            configuration = NetworkConfiguration(self, name, params)
            self._configurations[name] = configuration


    def update_configuration(self):
        """
        Here we check that what we want is inline with what is available in NetworkManager
        """
        _logger.debug("NetworkService updating configuration")
        self._network_manager.get_networking_conf()
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
        _logger.debug(f"NetworkService updating interface {interface.name} device {interface.device}")
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
        # now we need to link the configuration connection and the actual one
        try:
            connection = self._connections[interface.network_connection.name]
            interface.connection = connection
        except KeyError:
            _logger.error(
                f"NetworkService interface {interface.name} connection {device.connection} not found in the configuration file")
            return
        # now we need to understand better
        _logger.debug(f"NetworkService interface {interface.name} device {interface.device} connection {device.connection} state {device.state}")
        interface.state = device.state


    def apply_configuration(self, configuration_name:str):
        try:
            configuration = self._configurations[configuration_name]
        except KeyError:
            _logger.error(f"NetworkService configuration {configuration_name} not found")
            raise NetworkManagerError(121, f"Configuration {configuration_name} not found")
        for interface, connection in configuration.all_connections():
            self.apply_connection(interface, connection)

    def apply_connection(self, interface: NetworkInterface, connection: NetworkInterfaceConnection) -> str:
        _logger.debug(f"NetworkService applying connection {connection.name} for interface {interface.name}")
        if interface.state == "unmanaged":
            _logger.info(f"NetworkService interface {interface.name} device {interface.device} is unmanaged")
            raise NetworkManagerError(110, f"Interface {interface.name} is unmanaged")
        device = self._network_manager.get_device(interface.device)
        _logger.debug(f"NetworkService interface {interface.name} device {interface.device} state {device.state} => {device.connection}")
        if device.state == 'connected':
            if device.connection != connection.name:
                _logger.info(f"NetworkService actual connection for interface {interface.name} is {device.connection} => deleted")
                # lets delete it
                self._network_manager.delete_device_connection(device.connection)
            else:
                _logger.info(f"NetworkService interface {interface.name} device {interface.device} connection {device.connection} already set")
                return f"NetworkService interface {interface.name} device {interface.device} connection {device.connection} already set"
        # now we need to create the correct connection for the interface
        _logger.info(
            f"NetworkService creating connection {connection.name} for interface {interface.name} device {interface.device} with:{connection.params}")
        ret_val = self._network_manager.create_connection(connection.name, interface.device, interface.type, connection.params)
        self.update_interface(interface)
        return ret_val

    def connection_in_configuration(self, configuration_name: str, interface: NetworkInterface) -> NetworkInterfaceConnection:
        try:
            configuration = self._configurations[configuration_name]
        except KeyError:
            _logger.error(f"NetworkService configuration {configuration_name} not found")
            raise
        try:
            return configuration.connection_for_interface(interface.name)
        except KeyError:
            _logger.error(f"NetworkService interface {interface.name} not found in configuration {configuration_name}")
            raise

    def del_connection(self, interface:NetworkInterface) -> str:
        ret_val = self._network_manager.del_connection(interface.network_connection)
        self.update_interface(interface)
        return ret_val

    def up_connection(self, interface:NetworkInterface) -> str:
        if interface.connection is None:
            _logger.error(f"NetworkService interface {interface.name} has no connection configured")
            raise NetworkManagerError(f"NetworkService interface {interface.name} has no connection configured")
        ret_val = self._network_manager.up_connection(interface.connection)
        self.update_interface(interface)
        return ret_val

    def down_connection(self, interface:NetworkInterface) -> str:
        ret_val = self._network_manager.down_connection(interface.network_connection)
        self.update_interface(interface)
        return ret_val
