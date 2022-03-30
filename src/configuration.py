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
        self._param['name'] = self._name
        self._object = None

    @property
    def obj_class(self):
        return self._class

    def set_class(self, obj_class):
        self._class = obj_class

    @property
    def name(self):
        return self._name

    @property
    def object(self):
        return self._object

    def build_object(self):
        if self._class is None:
            try:
                self._class = NavigationConfiguration.get_conf().get_class(self._class_name)
            except KeyError:
                raise ConfigurationException("Missing class to build %s object" % self._name)
        factory = self._param.get('factory', None)
        if factory is None:
            self._object = self._class(self._param)
        else:
            self._object = getattr(self._class, factory)(self._param)
        return self._object


class NavigationConfiguration:

    _instance = None

    @staticmethod
    def get_conf():
        return NavigationConfiguration._instance

    def __init__(self, settings_file):
        self._configuration = None
        self._obj_dict = {}
        self._class_dict = {}
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
        NavigationConfiguration._instance = self

    def dump(self):
        print(self._configuration)

    def get_option(self, name, default):
        return self._configuration.get(name, default)

    def object_descr_iter(self, obj_type):
        servers = self._configuration[obj_type]
        if servers is None:
            # nothing to iterate
            _logger.info("No %s objects in the settings file" % obj_type)
            return
        for server in servers:
            yield server

    def servers(self):
        return self._servers.values()

    def instruments(self):
        return self._instruments.values()

    def publishers(self):
        return self._publishers.values()

    def add_class(self, class_object):
        self._class_dict[class_object.__name__] = class_object

    def get_class(self, name):
        return self._class_dict[name]

    def get_object(self, name):
        return self._obj_dict[name].object


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
