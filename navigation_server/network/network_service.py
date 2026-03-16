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
import json
import os.path
from collections import namedtuple
from socket import gethostname
import subprocess

_logger = logging.getLogger('ShipDataServer.' + __name__)

from navigation_server.router_common import GrpcService, GrpcServerError, get_global_var, fill_uuid_protobuf, MessageServerGlobals
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
    def support_ssl(self) -> bool:
        if self._connection is not None:
            return self._connection.support_ssl
        else:
            return False

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

    @property
    def ipv4_address(self):
        if self._network_connection is not None:
            return self._network_connection.ipv4_address
        elif self._connection is not None:
            return self._connection.ipv4_address
        else:
            raise ValueError(f"NetworkInterface {self._name} has no connection")

    @property
    def function(self):
        if self._connection is None:
            raise ValueError(f"NetworkInterface {self._name} has no connection")
        else:
            return self._connection.function


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
    def support_ssl(self) -> bool:
        return self._params.get('support_ssl', False)

    @property
    def network_connection(self):
        return self._network_connection

    @property
    def ipv4_address(self):
        if self._network_connection is not None:
            address = self._network_connection.ipv4_address
        else:
            address = self._params.get('ipv4_address', None)
        if address is not None:
            isl = address.find('/')
            if isl > 0:
                address = address[:isl]
        return address

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
InterfaceSSLConfiguration = namedtuple('InterfaceSSLConfiguration', ['interface', 'function', 'ipv4_address'])

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
        resp.status = "OK"
        resp.details = f"interfaces={len(resp.if_list)}"


class NetworkService(GrpcService):

    def __init__(self, opts):
        super().__init__(opts)
        self._configuration_file = opts.get('configuration', str, 'network_conf.yml')
        self._gen_ssl = opts.get('generate_ssl', bool, False)
        self._restart_ssl_config = opts.get('restart_ssl', bool, False)
        self._ipv6_ssl = opts.get('ipv6_ssl', bool, False)
        self._network_manager = NetworkManagerControl()
        self._modem_manager = ModemControl()
        self._servicer = None
        self._configuration = None
        self._interfaces = {}
        self._connections = {}
        self._configurations = {}
        self._saved_network_state = None
        self._apply_default = False
        # shall be last
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

    def interface_from_type(self, interface_type:str):
        for interface in self._interfaces.values():
            if interface.type == interface_type:
                return interface
        return None

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
        # let's see if we have to manage a modem
        if self.interface_from_type('cellular') is not None:
            if not self._modem_manager.detect():
                # ok the modem is not yet showing up
                _logger.info("No modem detected yet => starting power-on sequence")
                self._modem_manager.power_on_sequence(self.modem_update)
        self.update_configuration()
        # check that all interfaces have a connection
        for interface in self.interfaces():
            if interface.connection is None:
                _logger.info(f"NetworkService interface {interface.name} has no connection")
                if self._apply_default:
                    _logger.info(f"NetworkService interface {interface.name} applying default connection")
                    try:
                        connection = self.connection_in_configuration('default', interface)
                        self.apply_connection(interface, connection)
                    except NetworkManagerError as e:
                        _logger.error(f"NetworkService error applying default connection for interface {interface.name}: {e}")
                        continue
                    except KeyError:
                        _logger.error(f"NetworkService interface {interface.name} default connection not found")
                        continue

        # do we have to configure SSL on interfaces
        if self._gen_ssl:
            if self.generate_ssl_configuration():
                if self.generate_server_certificates():
                    if self._restart_ssl_config:
                        _logger.info(f"Stopping {MessageServerGlobals.server_name} to be restarted with new SSL configuration")
                        # ok we need to restart the navigation_server assuming AgentTopServer class
                        MessageServerGlobals.main_server.stop_navigation()
                    else:
                        _logger.warning(f"{MessageServerGlobals.server_name} must be restarted after new SSL configuration generated")

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

        self._apply_default = self._configuration.get('apply_default_connections', False)

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
            _logger.debug("NetworkService updating modem configuration")
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
        device = self._network_manager.get_device(interface.device)
        _logger.debug(f"NetworkService interface {interface.name} device {interface.device} state {device.state} => {device.connection}")
        if device.state == 'connected' or device.state == 'connecting':
            if device.connection != connection.name:
                _logger.info(f"NetworkService actual connection for interface {interface.name} is {device.connection} => deleted")
                # lets delete it
                self._network_manager.delete_device_connection(device.connection)
            else:
                _logger.info(f"NetworkService interface {interface.name} device {interface.device} connection {device.connection} already set")
                return f"NetworkService interface {interface.name} device {interface.device} connection {device.connection} already set"
        elif device.state == "unmanaged":
            _logger.info(f"NetworkService interface {interface.name} device {interface.device} is unmanaged")
            raise NetworkManagerError(110, f"Interface {interface.name} is unmanaged")
        elif device.state == 'disconnected':
            _logger.info(f"NetworkService interface {interface.name} device {interface.device} is disconnected")
            # we need to check that there no existing connection
            try:
                conn = self._network_manager.get_connection(connection.name)
            except KeyError:
                _logger.debug(f"NetworkService interface {interface.name} device {interface.device} connection {connection.name} not found")
            else:
                _logger.info(f"NetworkService interface {interface.name} device {interface.device} connection {connection.name} already exists")
                return f"NetworkService interface {interface.name} device {interface.device} connection {connection.name} already exists"
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

    def generate_ssl_configuration(self) -> bool:

        _logger.info("Check if the generation of a new configuration file is necessary")
        certificate_dir = get_global_var('certificate_dir')
        if certificate_dir is None:
            _logger.error("Missing certificate_dir global variable")
            return False
        try:
            with open(os.path.join(certificate_dir, 'ssl_network_state'), 'r') as fp:
                network_state = json.load(fp)
                self._saved_network_state = {}
                for state in network_state:
                    self._saved_network_state[state[0]] = InterfaceSSLConfiguration(state[0], state[1], state[2])
        except FileNotFoundError:
            _logger.info(f"No saved network state found: {certificate_dir}/ssl_network_state")
        except yaml.YAMLError as e:
            _logger.error(f"NetworkService error decoding saved network state file: {e}")

        intf_ssl_list = []
        need_to_generate = False
        for interface in self.interfaces():
            if interface.support_ssl:
                _logger.debug(f"NetworkService interface {interface.name} support_ssl=True")
                try:
                    intf_ssl_def = InterfaceSSLConfiguration(interface.name, interface.function, interface.ipv4_address)
                except ValueError as err:
                    _logger.error(f"NetworkService interface {interface.name} error:{err}")
                    continue
                if self._saved_network_state is not None:
                    intf_ssl_save = self._saved_network_state.get(interface.name, None)
                    if intf_ssl_save is not None:
                        if intf_ssl_save.ipv4_address == interface.ipv4_address and intf_ssl_save.function == interface.function:
                            _logger.debug(f"NetworkService interface {interface.name} ipv4_address unchanged")
                        else:
                            need_to_generate = True
                            _logger.info(
                                f"NetworkService interface {interface.name} ipv4_address changed from {intf_ssl_save.ipv4_address} to {interface.ipv4_address}")
                    else:
                        need_to_generate = True
                else:
                    need_to_generate = True
                # need to add the interface in all cases
                intf_ssl_list.append(intf_ssl_def)
        configuration_file = os.path.join(certificate_dir, 'nav_openssl.cnf')
        if not os.path.isfile(configuration_file):
            _logger.debug(f"NetworkService configuration file {configuration_file} not found")
            need_to_generate = True

        if need_to_generate:
            _logger.info("Generating SSL certificates and configuration files for interfaces")
            if self._ipv6_ssl:
                _logger.warning("NetworkService: IPv6 SSL certificates and configuration files generation is not supported yet")
            # ok, then we need to generate a new file
            _logger.info("Generating SSL configuration files")
            with open(os.path.join(certificate_dir, 'nav_openssl.cnf'), 'w') as fp:
                fp.write("""# This file is generated automatically do not modify
[req]
distinguished_name = req_distinguished_name
req_extensions = v3_req
prompt = no

[req_distinguished_name]
CN = localhost  # CN is required but can be localhost

[v3_req]
keyUsage = critical, keyEncipherment, dataEncipherment, digitalSignature
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]\n""")
                index_if = 1
                network_state = []
                for intf_ssl_def in intf_ssl_list:
                    fp.write(f"IP.{index_if} = {intf_ssl_def.ipv4_address}\t# {intf_ssl_def.interface}\n")
                    network_state.append((intf_ssl_def.interface, intf_ssl_def.function, intf_ssl_def.ipv4_address))
                    index_if += 1
                # always need to add localhost
                fp.write(f"IP.{index_if} = 127.0.0.1\t# localhost\n")
                fp.write(f"DNS.1 = {gethostname()}\n")
                with open(os.path.join(certificate_dir, 'ssl_network_state'), 'w') as fp2:
                    json.dump(network_state, fp2)
        else:
            _logger.debug("NetworkService SSL configuration not required")

        return need_to_generate

    def generate_server_certificates(self):
        _logger.info("Generating server certificates")
        certificate_dir = get_global_var('certificate_dir')
        if certificate_dir is None:
            _logger.error("Missing certificate_dir global variable")
            return False
        key_dir = get_global_var('ssl_key_dir')
        if key_dir is None:
            _logger.error("Missing ssl_key_dir global variable")
            return False
        server_ca_certificate = os.path.join(certificate_dir, 'nav_ca_cert.pem')
        server_ca_key = os.path.join(key_dir, 'nav_ca_key.pem')
        _logger.debug(f"key file: {server_ca_key} - certificate file: {server_ca_certificate}")
        if not os.path.isfile(server_ca_certificate) or not os.path.isfile(server_ca_key):
            _logger.error("Missing CA key and/or certificate to generate server certificates")
            return False
        server_certificate = os.path.join(certificate_dir, 'nav_server_cert.pem')
        server_key = os.path.join(certificate_dir, 'nav_server_key.pem')
        server_req = os.path.join(certificate_dir, 'nav_server_req.pem')
        conf_file = os.path.join(certificate_dir, 'nav_openssl.cnf')

        def run_openssl(cmd: list):
            _logger.debug(f"NetworkService running openssl command: {cmd}")
            args = ['openssl'] + cmd
            try:
                ret_val = subprocess.run(args, capture_output=True, check=True)
            except subprocess.CalledProcessError as e:
                _logger.error(f"NetworkService openssl command failed: {e}")
                raise ValueError(f"NetworkService openssl command failed: {e}")
            else:
                _logger.debug(f"NetworkService openssl command output: {ret_val.stdout}")
        _logger.info("Generating server certificate")

        try:
            run_openssl(['genrsa', '-out', server_key, '4096'])
            run_openssl(['req', '-new', '-key', server_key, '-out', server_req, '-config', conf_file])
            run_openssl(['x509', '-req', '-days', '365', '-in', server_req, '-CA', server_ca_certificate, '-CAkey',
                         server_ca_key, '-extfile',conf_file, '-out', server_certificate, '-extensions', 'v3_req'])
        except ValueError:
            _logger.error("NetworkService openssl command failed")
            return False

        # here we shall be good
        return True
