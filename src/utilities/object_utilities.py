#-------------------------------------------------------------------------------
# Name:        object utilities
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
