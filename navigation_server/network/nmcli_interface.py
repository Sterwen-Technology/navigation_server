#-------------------------------------------------------------------------------
# Name:        nmcli_interface.py
# Purpose:     provide an interface to nmcli to manage network devices and connections
#              That shall replace the existing ad-hoc quectel_modem Python library
# Author:      Laurent Carré
#
# Created:     27/03/2025
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from collections import namedtuple
import io
import socket
import uuid

_logger = logging.getLogger('ShipDataServer.' + __name__)


class NetworkManagerError(Exception):
    pass


def nmcli_request(command: list):
    """
    Sends a request to nmcli and returns a generator of list of tokens
    No interpretation
    """
    args = ["nmcli", "-t"] + command
    _logger.debug(f"nmcli request: {args}")
    result = subprocess.run(args, capture_output=True, encoding="utf-8")
    if result.returncode == 0:
        stream = io.StringIO(result.stdout)
        for line in stream:
            tokens = line[:-1].split(":")
            yield tokens
    else:
        _logger.error(result.stderr)
        raise NetworkManagerError(result.returncode)
    return

def nmcli_command(command: list):
    args = ["nmcli", "-t"] + command
    _logger.debug(f"nmcli command: {args}")
    result = subprocess.run(args, capture_output=True, encoding="utf-8")
    if result.returncode == 0:
        stream = io.StringIO(result.stdout)
        for line in stream:
            _logger.debug(f"nmcli command response {line[:-1]}")
    else:
        _logger.error(f"nmcli command {command} failed")
        stream = io.StringIO(result.stderr)
        for line in stream:
            _logger.error(f"nmcli command error message: {line[:-1]}")
        raise NetworkManagerError(result.returncode)
    return


@dataclass
class NetworkDevice:
    name: str
    type: str
    state: str
    connection: str = None

ConnParameterRef = namedtuple('ConnParameterRef', ['name', 'value'])

general_parameters = [
    ConnParameterRef('name', 'connection.id'),
    ConnParameterRef('uuid', 'connection.uuid'),
    ConnParameterRef('type', 'connection.type'),
    ConnParameterRef('state', 'connection.state'),
    ConnParameterRef('device', 'connection.interface-name'),
    ConnParameterRef('ipv4_method', 'ipv4.method'),
    ConnParameterRef('ipv4_address', 'IP4.ADDRESS[1]'),
    ConnParameterRef('ipv6_method', 'ipv6.method'),
    ConnParameterRef('ipv6_address', 'IP6.ADDRESS[1]'),
    ConnParameterRef('ipv4_gateway', 'IP4.GATEWAY'),
]

ethernet_parameters = general_parameters + []

wifi_specific_parameters = [
    ConnParameterRef('ssid', '802-11-wireless.ssid'),
    ConnParameterRef('mode', '802-11-wireless.mode'),
    ConnParameterRef('band', '802-11-wireless.band'),
    ConnParameterRef('channel', '802-11-wireless.channel'),
    ConnParameterRef('frequency', '802-11-wireless.frequency'),
    ConnParameterRef('bitrate', '802-11-wireless.bitrate'),
    ConnParameterRef('txpower', '802-11-wireless.txpower'),
    ConnParameterRef('security', '802-11-wireless.security.key-mgmt'),
    ConnParameterRef('password', '802-11-wireless-security.psk'),
]

wifi_parameters = general_parameters + wifi_specific_parameters

cellular_specific_parameters = [
    ConnParameterRef('apn', 'gsm.apn'),
    ConnParameterRef('username', 'gsm.username'),
    ConnParameterRef('password', 'gsm.password'),
]

cellular_parameters = general_parameters + cellular_specific_parameters

all_parameters = general_parameters + wifi_specific_parameters + cellular_specific_parameters

parameters_by_type = {
    "ethernet": {key for _, key in ethernet_parameters},
    "wifi": {key for _, key in wifi_parameters},
    "gsm": {key for _, key in cellular_parameters},
}

reverses_parameters_global = { key: value for value, key in all_parameters }


class NetworkConnection:

    _excluded_properties = { 'name', 'uuid', 'device'
                             }
    def __init__(self):
        self._properties = {}
        self._uuid = None

    def add_property(self, key, value):
        attribute = reverses_parameters_global[key]
        # _logger.debug(f"NetworkConnection adding property {attribute} from {key} = {value}")
        self._properties[attribute] = value
        if attribute == 'uuid':
            self._uuid = uuid.UUID(value)
            # _logger.debug(f"NetworkConnection set uuid from:{value} = {self._uuid}")

    @property
    def uuid(self) -> uuid.UUID:
        return self._uuid

    def get_property(self, key):
        return self._properties[key]

    def get_properties(self):
        for key, value in self._properties.items():
            if key not in self._excluded_properties:
                yield key, value

    def __getattr__(self, attribute):
        return self._properties[attribute]




class NetworkManagerControl:

    ethernet = {
        "WAN_INTERFACE": ['type', 'ethernet', 'ipv4.method', 'auto', 'ipv6.method', 'auto'],
        "LAN_INTERFACE": ['type', 'ethernet', 'ipv4.method', 'auto', 'ipv6.method', 'auto'],
        "LAN_CONTROLLER": ['type', 'ethernet', 'ipv4.method', 'shared', 'ipv6.method', 'auto'],
    }

    def __init__(self):

        self._nm_running = False
        self._general_status = None
        self._devices = {}
        self._connections = {}
        self._build_parameters = {
            'ethernet': self.gen_ethernet_parameters,
            'cellular': self.gen_cellular_parameters,
            'wifi': self.gen_wifi_parameters
        }

    def check_network_manager(self, wait:bool = True):
        def read_status():
            try:
                for reply in nmcli_request(['general', 'status']):
                   return reply
            except NetworkManagerError:
                _logger.critical("NetworkInterface NetworkManager not installed or not running")
                raise
        start = time.time()
        while not self._nm_running:
            self._general_status = read_status()
            _logger.debug(f"NetworkManager status: {self._general_status}")
            if self._general_status[0] == "connected":
                self._nm_running = True
                break
            if not wait:
                break
            if time.time() - start > 60:
                _logger.critical("NetworkInterface NetworkManager not running after 60s")
                raise NetworkManagerError("NetworkManager not running")
            else:
                time.sleep(10)

    @property
    def nm_running(self) -> bool:
        return self._nm_running

    def get_networking_conf(self):
        _logger.debug("NetworkInterface reading networking configuration")
        if not self._nm_running:
            _logger.error("NetworkInterface NetworkManager not running")
            raise NetworkManagerError("NetworkManager not running")

        for d in nmcli_request(["device"]):
            if d[1] in {'ethernet', 'wifi', 'gsm'}:
                dev = NetworkDevice(d[0], d[1], d[2], d[3])
                _logger.debug(f"nmcli Device detected {dev})")
                self._devices[dev.name] = dev

        # now get the connections
        for device in self._devices.values():
            if device.connection is not None and len(device.connection) > 0:
                self.read_network_connection(device.type, device.connection)

    def read_device_configuration(self, device_name:str, expected_type:str = None):
        _logger.debug(f"NetworkManager read device {device_name}")
        device_type = None
        device_state = None
        device_connection = None
        for line in nmcli_request(['device', 'show', device_name]):
            match line[0]:
                case 'GENERAL.DEVICE':
                    assert device_name == line[1]
                case 'GENERAL.TYPE':
                    device_type = line[1]
                    if expected_type is not None and expected_type != device_type:
                        raise ValueError(f"Device {device_name} is not a {expected_type}")
                case 'GENERAL.STATE':
                    device_state = line[1]
                case 'GENERAL.CONNECTION':
                    if len(line) > 1 and len(line[1]) > 0:
                        device_connection = line[1]

        device = NetworkDevice(device_name, device_type, device_state, device_connection)
        self._devices[device.name] = device
        if device_connection is not None:
            self.read_network_connection(device_type, device_connection)
        return device_type, device_state, device_connection

    def get_device(self, name):
        return self._devices[name]

    def device_update_connection(self, device_name: str, connection_name: str):
        self._devices[device_name].connection = connection_name

    def get_devices(self):
        return self._devices.values()

    def get_connections(self):
        return self._connections.values()

    def get_connection(self, name:str) -> NetworkConnection:
        return self._connections[name]

    def delete_device_connection(self, name:str):
        # only use in case on initial device setup
        _logger.debug(f"nmcli => Deleting connection {name}")
        try:
            conn = self._connections[name]
        except KeyError:
            _logger.error(f"NetworkInterface connection {name} not found")
            return
        nmcli_command(["con", "delete", conn.name])
        del self._connections[name]

    def read_network_connection(self, device_type, name):
        _logger.debug(f"nmcli => Reading connection {name} type {device_type}")
        conn = NetworkConnection()
        parameters_list = parameters_by_type[device_type]
        # _logger.debug(f"parameters:{parameters_list}")
        for property in nmcli_request(["con", "show", name]):
            # _logger.debug(f"NetworkManager read property {property}")
            if property[0] in parameters_list:
                conn.add_property(property[0], property[1])
        self._connections[conn.name] = conn



    def create_connection(self, name:str, device:str, connection_type:str, params:dict):
        if params is None:
            _logger.error(f"NetworkInterface create_connection: no parameters for connection {name}")
            return
        try:
            function = params['function']
        except KeyError:
            _logger.error(f"NetworkInterface create_connection: no function for connection {name}")
            return
        _logger.debug(f"nmcli => Creating connection {name} on device {device} of type {connection_type}: {function}")
        base_parameters = ['conn', 'add', 'ifname', device, 'con-name', name]
        try:
            if_parameters = self._build_parameters[connection_type](function, params)
        except KeyError:
            _logger.error(f"NetworkInterface create_connection: {name} parameters errors")
            return
        parameters = base_parameters + if_parameters
        try:
            nmcli_command(parameters)
        except NetworkManagerError:
            _logger.error(f"NetworkInterface create_connection: nmcli error for connection {name}")
            return
        self.device_update_connection(device, name)
        self.read_network_connection(connection_type, name)
        nmcli_command(['conn', 'up', name])
        self.read_network_connection(connection_type, name)

    def gen_ethernet_parameters(self, function, params) -> list:
        _logger.debug(f"ethernet_parameters: {function} {params}")
        base_list = self.ethernet[function]
        if function == "LAN_CONTROLLER":
            full_list = base_list + ['ipv4.addresses', f"{params['ipv4_address']}/24"]
        else:
            full_list = base_list
        _logger.debug(f"ethernet_parameters: {full_list}")
        return full_list

    def gen_cellular_parameters(self, function, params) -> list:
        parameters = ['type', 'gsm', 'gsm.apn', params['apn'], 'ipv4.method', 'auto', 'ipv6.method', 'auto']
        if params.get('username', None) is not None:
            parameters.extend(['gsm.username', params['username']])
        if params.get('password', None) is not None:
            parameters.extend(['gsm.password', params['password']])
        return parameters

    def gen_wifi_parameters(self, function, params) -> list:
        if function == "LAN_CONTROLLER":
            if params.get('ssid', None) is None:
                ssid = socket.gethostname()
            else:
                ssid = params['ssid']
            parameters = ['type', 'wifi', 'wifi.ssid', f'{ssid}', 'wifi.mode', 'ap', 'ipv4.method', 'shared',
                          'ipv6.method', 'shared', 'ipv4.addresses', f"{params['ipv4_address']}/24"]
            if params.get('password', None) is not None:
                parameters.extend(['wifi.psk', params['password'], 'wifi.key-mgmt', 'wpa-psk'])
            if params.get('band', None) is not None:
                parameters.extend(['wifi.band', params['band']])
        else:
            raise NotImplementedError
        return parameters

    def del_connection(self, conn:NetworkConnection):
        name = conn.name
        nmcli_command(['conn', 'delete', name])
        # make our internal cleanup
        del self._connections[name]
        # reload device
        self.read_device_configuration(conn.device, conn.type)

    def up_connection(self, conn:NetworkConnection):
        name = conn.name
        nmcli_command(['conn', 'up', name])
        self.read_network_connection(conn.type, name)

    def down_connection(self, conn:NetworkConnection):
        name = conn.name
        nmcli_command(['conn', 'up', name])
        self.read_device_configuration(conn.device, conn.type)









if __name__ == "__main__":

    nm = NetworkManagerControl()
    nm.get_networking_conf()
    for dev in nm.get_devices():
        print(dev)
    for connection in nm.get_connections():
        print(connection.name, connection.type, connection.ipv4_method, connection.ipv4_address)



