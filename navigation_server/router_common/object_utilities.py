#-------------------------------------------------------------------------------
# Name:        object router_common
# Purpose:     several functions to manipulate objects and attributes
#
# Author:      Laurent Carré
#
# Created:     23/10/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------


def copy_attribute(source, destination, attribute_list):
    for attr in attribute_list:
        destination.__setattr__(attr, source.__getattribute__(attr))


def build_subclass_dict(base_class) -> dict:
    '''
    Returns all subclasses from the base class (but not the base class itself)
    With recursion
    '''
    subclasses = {}

    def find_subclasses(base, result_dict: dict):
        for cls in base.__subclasses__():
            result_dict[cls.__name__] = cls
            find_subclasses(cls, result_dict)

    find_subclasses(base_class, subclasses)
    return subclasses
