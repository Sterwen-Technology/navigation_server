#-------------------------------------------------------------------------------
# Name:        data_configuration
# Purpose:     Decodes the Yaml configuration and build the structure in memory
# Author:      Laurent Carré
#
# Created:     01/08/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import yaml

from nmea_data.data_element import DataElementSet

_logger = logging.getLogger("ShipDataServer." + __name__)


class NavigationDataConfiguration:

    _instance = None

    @staticmethod
    def get_conf():
        return NavigationDataConfiguration._instance

    def __init__(self, configuration_file_name: str):
        try:
            fp = open(configuration_file_name, 'r')
        except IOError as e:
            _logger.error("Settings file %s error %s" % (configuration_file_name, e))
            raise
        try:
            self._configuration = yaml.load(fp, yaml.FullLoader)
        except yaml.YAMLError as e:
            _logger.error("Settings file decoding error %s" % str(e))
            fp.close()
            raise
        NavigationDataConfiguration._instance = self
        self._elements = DataElementSet()
        for obj in self.object_iter('dictionary'):
            print(obj['element'])
            self._elements.create_element(obj['element'])
        for elem in self._elements.get_elements():
            print(elem.code, elem.description)

    def get_option(self, name, default):
        return self._configuration.get(name, default)

    def object_iter(self, section):
        elements = self._configuration[section]
        if elements is None:
            # nothing to iterate
            _logger.info("No %s objects in the settings file" % section)
            return
        for element in elements:
            yield element

