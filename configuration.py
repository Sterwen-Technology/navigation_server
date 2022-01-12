#-------------------------------------------------------------------------------
# Name:        ShipModul_if
# Purpose:     ShipModule interface
#
# Author:      Laurent Carré
#
# Created:     08/01/2022
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-20222
# Licence:     <your licence>
#-------------------------------------------------------------------------------

import yaml
import logging
import sys

_logger = logging.getLogger("ShipDataServer")


class ConfigurationException(Exception):
    pass


class NavigationServerObject:

    def __init__(self, class_descr):
        for item in class_descr.items():
            self._name = item[0]
            self._param = item[1]
        self._class = None
        self._class_name = self._param['class']

    @property
    def obj_class(self):
        return self._class

    def set_class(self, obj_class):
        self._class = obj_class

    @property
    def name(self):
        return self._name

    def build_object(self):
        if self._class is None:
            raise ConfigurationException("Missing class to build %s object" % self._name)
        factory = self._param.get('factory', None)
        if factory is None:
            return self._class(self._param)
        else:
            return self._class.getattr(factory)(self._param)

class NavigationConfiguration:

    def __init__(self, settings_file):
        self._configuration = None
        self._obj_dict = {}
        self._servers = {}
        self._instruments = {}
        self._publishers = {}
        try:
            fp = open(settings_file, 'r')
        except IOError as e:
            print(e)
            _logger.error("Settings file %s" % str(e))
            raise
        try:
            self._configuration = yaml.load(fp, yaml.FullLoader)
        except yaml.YAMLError as e:
            print(e)
            _logger.error("Settings file decoding error %s" % str(e))
            raise
        for obj in self.object_descr_iter('servers'):
            nav_obj = NavigationServerObject(obj)
            self._obj_dict[nav_obj.name] = nav_obj
            self._servers[nav_obj.name] = nav_obj
        for obj in self.object_descr_iter('instruments'):
            nav_obj = NavigationServerObject(obj)
            self._obj_dict[nav_obj.name] = nav_obj
            self._instruments[nav_obj.name] = nav_obj
        for obj in self.object_descr_iter('publishers'):
            nav_obj = NavigationServerObject(obj)
            self._obj_dict[nav_obj.name] = nav_obj
            self._publishers[nav_obj.name] = nav_obj

    def dump(self):
        print(self._configuration)

    def get_option(self, name, default):
        self._configuration.get(name, default)

    def object_descr_iter(self, obj_type):
        servers = self._configuration[obj_type]
        for server in servers:
            yield server

    def servers(self):
        return self._servers

    def add_class(self, class_object):
        try:
            self._obj_dict[class_object.__name__].set_class(class_object)
        except KeyError:
            _logger.error("No object configured for Python class:%s" % class_object.__name__)




def main():
    file = sys.argv[1]
    conf = NavigationConfiguration(file)
    # conf.dump()
    for server in conf.object_descr_iter('servers'):
        print(server)
        items = server.items()
        for item in items:
            name = item[0]
            param = item[1]
        print(name, param)


if __name__ == '__main__':
    main()
