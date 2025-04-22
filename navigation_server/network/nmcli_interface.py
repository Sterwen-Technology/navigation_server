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
import io
from lib2to3.btm_utils import reduce_tree

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

@dataclass
class NetworkDevice:
    name: str
    type: str
    state: str
    connection: str = None


class NetworkConnection:

    _attr_properties = {
        'name': 'connection.id',
        'device': 'connection.interface-name',
        'type': 'connection.type',
        'state': 'connection.state',
        'ipv4_method': 'ipv4.method',
        'ipv4_address': 'ipv4.addresses',
        'ipv6_method': 'ipv6.method',
    }

    def __init__(self):
        self._properties = {}

    def add_property(self, key, value):
        self._properties[key] = value

    def get_property(self, key):
        return self._properties[key]

    def __getattr__(self, item):
        try:
            attribute = self._attr_properties[item]
        except KeyError:
            raise AttributeError
        else:
            return self._properties[attribute]


class NetworkManagerControl:

    ethernet = {
        "WAN_INTERFACE": ['type', 'ethernet', 'ipv4.method', 'auto', 'ipv6.method', 'auto'],
        "LAN_INTERFACE": ['type', 'ethernet', 'ipv4.method', 'auto', 'ipv6.method', 'auto'],
        "LAN_CONTROLLER": ['type', 'ethernet', 'ipv4.method', 'shared', 'ipv6.method', 'shared'],
    }

    def __init__(self):

        self._nm_running = False
        self._general_status = None
        self._devices = {}
        self._connections = {}
        self._build_parameters = {
            'ethernet': self.ethernet_parameters,
            'cellular': self.cellular_parameters,
            'wifi': self.wifi_parameters
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
        if not self._nm_running:
            _logger.error("NetworkInterface NetworkManager not running")
            raise NetworkManagerError("NetworkManager not running")

        for d in nmcli_request(["device"]):
            if d[1] in {'ethernet', 'wifi', 'gsm'}:
                dev = NetworkDevice(d[0], d[1], d[2], d[3])
                self._devices[dev.name] = dev

        # now get the connections
        for device in self._devices.values():
            if device.connection is not None and len(device.connection) > 0:
                self.read_connection(device.connection)

    def get_device(self, name):
        return self._devices[name]

    def get_devices(self):
        return self._devices.values()

    def get_connections(self):
        return self._connections.values()

    def get_connection(self, name:str) -> NetworkConnection:
        return self._connections[name]

    def delete_connection(self, name):
        try:
            conn = self._connections[name]
        except KeyError:
            _logger.error(f"NetworkInterface connection {name} not found")
            return
        nmcli_request(["con", "delete", conn.name])
        del self._connections[name]

    def read_connection(self, name):
        conn = NetworkConnection()
        for property in nmcli_request(["con", "show", name]):
            conn.add_property(property[0], property[1])
        self._connections[conn.name] = conn

    def create_connection(self, name:str, device:str, connection_type:str, params:dict):
        function = params['function']
        parameters = (['conn', 'add', 'ifname', device, 'conn-name', name] +
                      self._build_parameters[connection_type](function, params))
        nmcli_request(parameters)
        nmcli_request(['conn', 'up', name])
        self.read_connection(name)

    def ethernet_parameters(self, function, params) -> list:
        base_list = self.ethernet[function]
        if function == "LAN_CONTROLLER":
            full_list = base_list + ['ipv4.addresses', f"{params['ipv4_address']}/24"]
        else:
            full_list = base_list
        return full_list

    def cellular_parameters(self, function, params) -> list:
        parameters = ['type', 'gsm', 'gsm.apn', params['apn']]
        if params.get('username', None) is not None:
            parameters.extend(['gsm.username', params['username']])
        if params.get('password', None) is not None:
            parameters.extend(['gsm.password', params['password']])
        return parameters

    def wifi_parameters(self, function, params) -> list:
        if function == "LAN_CONTROLLER":
            parameters = ['type', 'wifi', 'wifi.ssid', params['ssid'], 'wifi.mode', 'infrastructure', 'ipv4.mode', 'shared',
                          'ipv6.mode', 'shared', 'ipv4.addresses', f"{params['ipv4_address']}/24"]
            if params.get('password', None) is not None:
                parameters.extend(['wifi.psk', params['password'], 'wifi.key-mgmt', 'wpa-psk'])
            if params.get('band', None) is not None:
                parameters.extend(['wifi.band', params['band']])
        else:
            raise NotImplementedError
        return parameters

    def device_up(self, name):
        nmcli_request(['device', 'up', name])

    def device_down(self, name):
        nmcli_request(['device', 'down', name])








if __name__ == "__main__":

    nm = NetworkManagerControl()
    nm.get_networking_conf()
    for dev in nm.get_devices():
        print(dev)
    for connection in nm.get_connections():
        print(connection.name, connection.type, connection.ipv4_method, connection.ipv4_address)



