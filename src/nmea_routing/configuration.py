#-------------------------------------------------------------------------------
# Name:        configuration
# Purpose:     Decode Yaml configuration file and manage the related objects
#
# Author:      Laurent Carré
#
# Created:     08/01/2022
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2024
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import yaml
import logging
import sys

from utilities.global_exceptions import ObjectCreationError

_logger = logging.getLogger("ShipDataServer."+__name__)


class ConfigurationException(Exception):
    pass


class Parameters:

    def __init__(self, param: dict):
        self._param = param

    def __getitem__(self, p_name):
        return self._param[p_name]

    @staticmethod
    def convert(p_name, p_type, value):
        if p_type == str:
            return str(value)
        elif p_type == bytes:
            return bytes(str(value).encode())
        elif p_type == bool:
            if type(value) == bool:
                return value
            else:
                raise ValueError
        elif p_type == int:
            if type(value) == int:
                return value
            else:
                _logger.warning("Parameter %s expected int" % p_name)
                raise ValueError
        elif p_type == float:
            if type(value) == float:
                return value
            else:
                try:
                    return float(value)
                except ValueError:
                    _logger.warning("Parameter %s expected float" % p_name)
                    raise
        else:
            _logger.error("Not supported type %s for parameter %s" % (str(p_type), p_name) )
            raise ValueError

    def getv(self, p_name):
        try:
            return self._param[p_name]
        except KeyError:
            return "Unknown parameter"

    def get(self, p_name, p_type, default):
        try:
            value = self._param[p_name]
        except KeyError:
            if default is None:
                return None
            value = default
        return self.convert(p_name, p_type, value)

    def getlist(self, p_name, p_type, default=None):
        try:
            value = self._param[p_name]
        except KeyError:
            return default

        if issubclass(type(value), list):
            val_list = []
            for v in value:
                val_list.append(self.convert('list item for %s' % p_name, p_type, v))
            return val_list
        else:
            _logger.warning("Parameter %s expected a list" % p_name)
            return default

    def get_choice(self, p_name, p_list, default):
        try:
            value = self._param[p_name]
        except KeyError:
            return default
        if value not in p_list:
            _logger.error("Incorrect value %s for %s" % (value, p_name))
            return default
        return value


class NavigationServerObject:

    def __init__(self, class_descr):
        for item in class_descr.items():
            self._name = item[0]
            self._param = item[1]
        self._class = None
        self._class_name = self._param['class']
        self._param['name'] = self._name
        self._object = None
        # self._instance = self

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
        try:
            if factory is None:
                self._object = self._class(Parameters(self._param))
            else:
                self._object = getattr(self._class, factory)(Parameters(self._param))
            return self._object
        except (TypeError, ObjectCreationError) as e:
            _logger.error("Error building object %s class %s: %s" % (self._name, self._class_name, e))
            raise ObjectCreationError("Error building object %s class %s: %s" % (self._name, self._class_name, e))

    def __str__(self):
        return "Object %s class %s object %s" % (self._name, self._class, self._object)


class NavigationConfiguration:

    _instance = None

    @staticmethod
    def get_conf():
        return NavigationConfiguration._instance

    def __init__(self, settings_file):
        # print ("Logger", _logger.getEffectiveLevel(), _logger.name)
        self._configuration = None
        self._obj_dict = {}
        self._class_dict = {}
        self._servers = {}
        self._couplers = {}
        self._publishers = {}
        self._services = {}
        self._filters = {}
        self._applications = {}
        self._globals = {}
        try:
            fp = open(settings_file, 'r')
        except IOError as e:
            _logger.error("Settings file %s error %s" % (settings_file, e))
            raise
        try:
            self._configuration = yaml.load(fp, yaml.FullLoader)
        except yaml.YAMLError as e:
            _logger.error("Settings file decoding error %s" % str(e))
            fp.close()
            raise
        for obj in self.object_descr_iter('servers'):
            nav_obj = NavigationServerObject(obj)
            self._obj_dict[nav_obj.name] = nav_obj
            self._servers[nav_obj.name] = nav_obj
        try:
            for obj in self.object_descr_iter('couplers'):
                nav_obj = NavigationServerObject(obj)
                self._obj_dict[nav_obj.name] = nav_obj
                self._couplers[nav_obj.name] = nav_obj
        except KeyError:
            _logger.info("No couplers")
        try:
            for obj in self.object_descr_iter('publishers'):
                nav_obj = NavigationServerObject(obj)
                self._obj_dict[nav_obj.name] = nav_obj
                self._publishers[nav_obj.name] = nav_obj
        except KeyError:
            _logger.info("No publishers")
        try:
            for obj in self.object_descr_iter('services'):
                nav_obj = NavigationServerObject(obj)
                self._obj_dict[nav_obj.name] = nav_obj
                self._services[nav_obj.name] = nav_obj
        except KeyError:
            _logger.info("No data clients")
        try:
            for obj in self.object_descr_iter('filters'):
                nav_obj = NavigationServerObject(obj)
                self._obj_dict[nav_obj.name] = nav_obj
                self._filters[nav_obj.name] = nav_obj
        except KeyError:
            _logger.info("No filters")
        try:
            for obj in self.object_descr_iter('applications'):
                nav_obj = NavigationServerObject(obj)
                self._obj_dict[nav_obj.name] = nav_obj
                self._applications[nav_obj.name] = nav_obj
        except KeyError:
            _logger.info("No applications")
        NavigationConfiguration._instance = self
        _logger.info("Finished analyzing settings file:%s " % settings_file)

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

    def couplers(self):
        return self._couplers.values()

    def coupler(self, name):
        return self._couplers[name]

    def publishers(self):
        return self._publishers.values()

    def services(self):
        return self._services.values()

    def filters(self):
        return self._filters.values()

    def applications(self):
        return self._applications.values()

    def add_class(self, class_object):
        self._class_dict[class_object.__name__] = class_object

    def get_class(self, name):
        return self._class_dict[name]

    def get_object(self, name):
        try:
            return self._obj_dict[name].object
        except KeyError:
            _logger.error("No object named: %s" % name)
            raise

    def set_global(self, key, obj):
        self._globals[key] = obj

    def get_global(self, key):
        try:
            return self._globals[key]
        except KeyError:
            _logger.error("Global reference %s non existent" % key)


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
