#-------------------------------------------------------------------------------
# Name:        protobuf_arguments
# Purpose:     Set of functions and classes for handling variable list of arguments
#
# Author:      Laurent Carré
#
# Created:     09/08/2022
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import datetime
from generated.arguments_pb2 import *


def protob_to_dict(arg_list) -> dict:
    res = {}
    for arg in arg_list:
        key = arg.key
        if arg.HasField('str_v'):
            val = arg.str_v
        elif arg.HasField('int_v'):
            val = arg.int_v
        elif arg.HasField('float_v'):
            val = arg.float_v
        elif arg.HasField('date_v'):
            val = datetime.datetime.fromisoformat(arg.date_v)
        else:
            continue
        res[key] = val
    return res


def dict_to_protob(arg_dict) -> ArgumentList:
    res = ArgumentList()
    for key, val in arg_dict:
        arg = res.add()
        arg.key = key
        if type(val) == str:
            arg.str_v = val
        elif type(val) == int:
            arg.int_v = val
        elif type(val) == float:
            arg.float_v = val
        elif type(val) == datetime.datetime:
            arg.date_v = val.isoformat()
        else:
            raise ValueError



