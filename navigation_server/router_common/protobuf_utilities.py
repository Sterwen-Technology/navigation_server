#-------------------------------------------------------------------------------
# Name:        protobuf_utilities
# Purpose:     Set of functions and classes implementing recurring functions
#               to handle protobuf data
#
# Author:      Laurent Carré
#
# Created:     09/08/2022
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------


def set_protobuf_data(result, keys, data_dict: dict):
    '''
    Assign the data contained in the dictionary to the protobuf structure
    :param result: protobuf generated class
    :param keys: list of tuples
    :param data_dict: dictionary with the data
    :return: None
    '''
    for key, attr, type_v, scale in keys:
        try:
            if type_v is not None and scale is not None:
                val = type_v(data_dict[key]) * scale
            else:
                val = data_dict[key]
            setattr(result, attr, val)
        except KeyError:
            continue

def fill_protobuf_from_dict(result, data_dict:dict):
    for key, val in data_dict.items():
        setattr(result, key, val)


def copy_protobuf_data(source, target, attributes):
    '''
    Copy the attributes in the iterator from source to target
    That is assuming that attributes have the same name in both objects
    '''
    for attr in attributes:
        setattr(target, attr, getattr(source, attr))


def pb_enum_string(msg, enum_attr: str, value):
    return msg.DESCRIPTOR.fields_by_name[enum_attr].enum_type.values_by_number[value].name


class ProtobufProxy:
    '''
    Abstract class to encapsulate access to protobuf message elements
    '''

    def __init__(self, msg):
        self._msg = msg

    def __getattr__(self, item):
        try:
            return self._msg.__getattribute__(item)
        except AttributeError:
            raise


class GrpcAccessException(Exception):
    pass

