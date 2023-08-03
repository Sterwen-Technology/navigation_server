#-------------------------------------------------------------------------------
# Name:        data_element
# Purpose:     Set of classes to support navigation data elements values and
#               behavior
# Author:      Laurent Carré
#
# Created:     01/08/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging


_logger = logging.getLogger("ShipDataServer." + __name__)


class DataElement:

    def __init__(self, param: dict):

        self._code = param['code']
        self._description = param.get('description', None)
        self._timestamp = 0.0
        self._value = None

    @property
    def code(self):
        return self._code

    @property
    def description(self):
        return self._description


class Float(DataElement):

    def __init__(self, param: dict):
        super().__init__(param)


class DataElementSet:

    _types_to_classes = {
        "Float": Float
    }

    def __init__(self):
        self._elements = {}

    def create_element(self, param:dict):
        class_name = param['type']
        element = self._types_to_classes[class_name](param)
        self._elements[element.code] = element

    def get_element(self, code):
        try:
            return self._elements[code]
        except KeyError:
            _logger.error("Element %s non existent" % code)
            raise

    def get_elements(self):
        return self._elements.values()


