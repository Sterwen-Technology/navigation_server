#-------------------------------------------------------------------------------
# Name:        configuration
# Purpose:     Decode Yaml configuration file and manage the related objects
#
# Author:      Laurent Carré
#
# Created:     08/01/2022 - new version with features 20/03/2024
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import inspect
import yaml
import logging
import sys
import importlib
import os
import os.path

from navigation_server.router_common import ObjectCreationError, MessageServerGlobals, ObjectFatalError, ConfigurationException
from .grpc_server_service import GrpcServer
from .generic_top_server import GenericTopServer
from .nav_threading import NavProfilingController, NavThreadingController

_logger = logging.getLogger("ShipDataServer."+__name__)


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
            if type(value) is bool:
                return value
            else:
                raise ValueError
        elif p_type == int:
            if type(value) is int:
                return value
            else:
                _logger.warning("Parameter %s expected int" % p_name)
                raise ValueError
        elif p_type == float:
            if type(value) is float:
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


class Feature:
    """
    The Feature class loads a software feature (a Python package)
    """

    def __init__(self, name: str,  package, configuration, package_items):
        """

        """
        self._name = name
        self._package = package
        self._configuration = configuration
        self._classes = {}
        self._init_function = None
        for obj_name, obj in inspect.getmembers(package):
            _logger.debug("Package %s object %s" % (name, obj_name))
            if inspect.isclass(obj):
                if package_items is not None:
                    # check if we need it
                    if obj_name not in package_items:
                        continue
                # we are good
                _logger.debug(f"Adding class:{obj_name}")
                self._configuration.add_class(obj)
                self._classes[obj_name] = obj
            elif inspect.isfunction(obj):
                if obj_name == 'initialize_feature':
                    # we got it !
                    self._init_function = obj

    def initialize(self, options):
        if self._init_function is not None:
            self._init_function(options)


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
                raise ConfigurationException("Missing class to build %s object" % self._class_name)
        factory = self._param.get('factory', None)
        try:
            if factory is None:
                self._object = self._class(Parameters(self._param))
            else:
                self._object = getattr(self._class, factory)(Parameters(self._param))
            return self._object
        except (TypeError, ObjectCreationError, ValueError) as e:
            _logger.error("Error building object %s class %s: %s" % (self._name, self._class_name, e))
            raise ObjectCreationError("Error building object %s class %s: %s" % (self._name, self._class_name, e))

    def __str__(self):
        return "Object %s class %s object %s" % (self._name, self._class, self._object)


class NavigationConfiguration:

    _instance = None

    @staticmethod
    def get_conf():
        return NavigationConfiguration._instance

    def __init__(self):
        # print ("Logger", _logger.getEffectiveLevel(), _logger.name)
        assert self._instance is None
        self._configuration = None
        self._obj_dict = {}
        self._class_dict = {}
        self._servers = {}
        self._couplers = {}
        self._publishers = {}
        self._services = {}
        self._filters = {}
        self._applications = {}
        self._functions = {}
        self._globals = {}
        self._features = {}
        self._hooks = {}
        self._processes = {} # new in version 2.4 only for the main agent
        self._main = None
        self._main_server = None
        self._settings_file = None
        self._server_purpose = None
        NavigationConfiguration._instance = self
        MessageServerGlobals.configuration = self
        # self.init_server_globals()

    def build_configuration(self, settings_file):
        """
        Build the full server configuration from the Yaml settings file
        raise Exceptions if the configuration fails
        """
        MessageServerGlobals.global_variables = self
        # print(settings_file)
        if not os.path.exists(settings_file):
            # we merge with the home dir
            settings_file = os.path.join(MessageServerGlobals.home_dir, "conf", settings_file)
        # keep the configuration path
        settings_path = os.path.dirname(settings_file)
        self.set_global('settings_path', settings_path)
        _logger.info(
            "Building configuration from settings file %s in path %s" % (settings_file, settings_path)
        )
        try:
            fp = open(settings_file, 'r')
        except (IOError, FileNotFoundError) as e:
            _logger.error("Settings file %s error %s" % (settings_file, e))
            _logger.error(f"Current directory is {os.getcwd()}")
            raise
        try:
            self._configuration = yaml.safe_load(fp)
        except yaml.YAMLError as e:
            _logger.error("Settings file decoding error %s" % str(e))
            fp.close()
            raise
        # check if we debug the configuration analysis
        if self._configuration.get('debug_configuration', False):
            _logger.setLevel(logging.DEBUG)
        # set the server name
        try:
            MessageServerGlobals.server_name = self._configuration['server_name']
        except KeyError:
            _logger.warning("Configuration: Missing the server name global parameter")
            MessageServerGlobals.server_name = "MessageServer(Default)"
        _logger.info(f"Server name: {MessageServerGlobals.server_name}")
        # display the server purpose
        try:
            server_purpose = self._configuration['function']
        except KeyError:
            server_purpose = 'Unknown'
            self._configuration['function'] = 'Unknown (missing "function" keyword)'
        _logger.info(f"Server function {server_purpose}")
        self._server_purpose = server_purpose
        try:
            data_directory = self._configuration['data_dir']
        except KeyError:
            base_directory, app_dir = os.path.split(os.getcwd())
            data_directory = os.path.join(base_directory, 'data')
        if os.path.isdir(data_directory):
            if os.access(data_directory,os.R_OK | os.W_OK | os.X_OK):
                MessageServerGlobals.data_dir = data_directory
                _logger.info(f"Data directory:{data_directory}")
            else:
                _logger.error(f"Not enough permissions for data_directory:{data_directory}")
        else:
            _logger.error(f"Non existent data directory {data_directory} - some features will not work")

        try:
            trace_dir = self._configuration['trace_dir']
        except KeyError:
            trace_dir = '/var/log'
        if not os.access(trace_dir, os.R_OK | os.W_OK | os.X_OK):
            _logger.warning(f"Trace directory {trace_dir} not existing => switching to /var/log")
            trace_dir = '/var/log'
        MessageServerGlobals.trace_dir = trace_dir

        try:
            MessageServerGlobals.agent_address = self._configuration['agent_address']
        except KeyError:
            MessageServerGlobals.agent_address = "127.0.0.1:4545"
            _logger.warning(f"Missing agent address, defaulting to {MessageServerGlobals.agent_address}")

        # create entries for allways included classes
        self.import_internal()
        for feature in self.object_descr_iter('features'):
            # import the required package from the configuration file
            self.import_feature(feature)
        for obj in self.object_descr_iter('servers'):
            nav_obj = NavigationServerObject(obj)
            if nav_obj.name == 'Main':
                self._main = nav_obj
            else:
                self._obj_dict[nav_obj.name] = nav_obj
                self._servers[nav_obj.name] = nav_obj
        if self._main is None:
            _logger.error("The 'Main' server is missing -> invalid configuration")
            raise ConfigurationException

        def read_objects(category, holding_dict):
            try:
                for obj in self.object_descr_iter(category):
                    nav_obj = NavigationServerObject(obj)
                    self._obj_dict[nav_obj.name] = nav_obj
                    holding_dict[nav_obj.name] = nav_obj
            except KeyError:
                _logger.info(f"No {category} in configuration")

        read_objects('processes', self._processes)
        read_objects('couplers', self._couplers)
        read_objects('publishers', self._publishers)
        read_objects('services', self._services)
        read_objects('filters', self._filters)
        read_objects('applications', self._applications)
        read_objects('functions', self._functions)

        # configure profiling
        profiler_conf = self._configuration.get('profiling', None)
        if profiler_conf is not None:
            MessageServerGlobals.profiling_controller.configure(self, profiler_conf)
        _logger.info("Finished analyzing settings file:%s " % settings_file)
        self._settings_file = settings_file
        return self

    @staticmethod
    def init_server_globals():
        MessageServerGlobals.thread_controller = NavThreadingController()
        MessageServerGlobals.profiling_controller = NavProfilingController()

    def dump(self):
        print(self._configuration)

    def get_option(self, name, default):
        return self._configuration.get(name, default)

    def object_descr_iter(self, obj_type):
        impl_obj_list = self._configuration[obj_type]
        if impl_obj_list is None:
            # nothing to iterate
            _logger.info("No %s objects in the settings file" % obj_type)
            return
        for impl_obj in impl_obj_list:
            yield impl_obj

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

    def processes(self):
        return self._processes.values()

    def functions(self):
        return self._functions.values()

    @property
    def main_server(self):
        return self._main_server

    @property
    def settings_file(self) -> str:
        return self._settings_file

    @property
    def server_purpose(self) -> str:
        return self._server_purpose

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

    def store_hook(self, key, hook):
        self._hooks[key] = hook

    def get_hook(self, key):
        return self._hooks[key]

    def import_internal(self):

        self.add_class(GrpcServer)
        self.add_class(GenericTopServer)

    def import_feature(self, feature):
        if type(feature) is str:
            package_name = feature
            package_items = None
        else:
            package_name, package_items = feature.popitem()

        _logger.info(f"Include feature {package_name} with objects:")
        try:
            full_package_name = f"{MessageServerGlobals.root_package}.{package_name}"
            package = importlib.import_module(full_package_name)
        except ImportError as err:
            _logger.error("Error importing package %s: %s" % (package_name, str(err)))
            return
        self._features[package_name] = Feature(package_name, package, self, package_items)

    def initialize_features(self, options):
        for feature in self._features.values():
            feature.initialize(options)

    def build_objects(self):
        _logger.debug("Configuration: creating main server")
        self._main_server = self._main.build_object()
        # create the filters upfront
        for inst_descr in self._filters.values():
            try:
                inst_descr.build_object()
            except ConfigurationException as e:
                _logger.error(str(e))
                continue
        _logger.debug("Filters created")
        for inst_descr in self._applications.values():
            try:
                inst_descr.build_object()
            except ConfigurationException as e:
                _logger.error(str(e))
                continue
        _logger.debug("Applications created")
        # create the servers
        for server_descr in self._servers.values():
            try:
                server = server_descr.build_object()
            except (ConfigurationException, ObjectCreationError, ObjectFatalError) as e:
                _logger.error("Error building server %s" % e)
                continue
            self._main_server.add_server(server)
        _logger.debug("Servers created")
        # create the services and notably the Console
        for data_s in self._services.values():
            try:
                service = data_s.build_object()
            except (ConfigurationException, ObjectCreationError, ObjectFatalError) as e:
                _logger.error("Error building service:%s" % e)
                continue
            self._main_server.add_service(service)
        if not self._main_server.console_present:
            _logger.warning("No console defined")
        _logger.debug("Services created")
        for inst_descr in self._functions.values():
            try:
                function = inst_descr.build_object()
            except (ConfigurationException, ObjectCreationError, ObjectFatalError) as e:
                _logger.error(f"Error building function:{inst_descr.name}:{e}")
                continue
            self._main_server.add_function(function)
        # create the couplers
        for inst_descr in self._couplers.values():
            try:
                coupler = inst_descr.build_object()
            except (ConfigurationException, ObjectCreationError, ObjectFatalError) as e:
                _logger.error("Error building Coupler:%s" % str(e))
                continue
            self._main_server.add_coupler(coupler)
            if self._main_server.console_present:
                self._main_server.console.add_coupler(coupler)
        _logger.debug("Couplers created")
        # create the publishers
        for pub_descr in self._publishers.values():
            try:
                publisher = pub_descr.build_object()
                self._main_server.add_publisher(publisher)
            except ConfigurationException as e:
                _logger.error(str(e))
                continue
        _logger.debug("Publishers created")
        # create the processes - only in agent
        if self._main_server.is_agent():
            self._main_server.pre_build()
        for proc_descr in self._processes.values():
            try:
                process = proc_descr.build_object()
                self._main_server.add_process(process)
            except ConfigurationException as e:
                _logger.error(str(e))
                continue



def main():
    file = sys.argv[1]
    conf = NavigationConfiguration().build_configuration(file)
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
