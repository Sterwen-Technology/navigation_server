#-------------------------------------------------------------------------------
# Name:        protobuf_utilities
# Purpose:     Set of functions and classes implementing recurring functions
#               to handle protobuf data
#
# Author:      Laurent Carré
#
# Created:     09/08/2022
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2022
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
            object.__setattr__(result, attr, val)
        except KeyError:
            continue
