# -------------------------------------------------------------------------------
# Name:        NMEA2K- Find the right decoding classes and dispatch the message
# Purpose:
#
# Author:      Laurent Carré
# Created:     01/10/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
# -------------------------------------------------------------------------------

import logging

from navigation_server.generated.nmea2000_classes_gen import nmea2k_generated_classes
from navigation_server.generated.nmea2000_pb2 import nmea2000_decoded_pb
from navigation_server.nmea2000_datamodel import PGNDef
from navigation_server.router_core import NMEA2000Msg

_logger = logging.getLogger("ShipDataServer." + __name__)


class N2KMissingDecodeEncodeException(Exception):
    pass


def get_n2k_decoded_object(msg: NMEA2000Msg):
    """
    Retrieves and decodes the corresponding NMEA2000 object for the provided NMEA2000 message.

    This function maps a given NMEA2000 message to its appropriate decoded object using predefined
    decoding classes. It identifies the correct class based on the message's PGN (Parameter Group
    Number). For proprietary PGNs, it additionally uses the manufacturer's ID to determine the
    specific class for decoding.

    Parameters:
    msg (NMEA2000Msg): The NMEA2000 message to decode.

    Returns:
    DecodedNMEA2000Object: An instance of the decoded object for the given NMEA2000 message.

    Raises:
    N2KMissingDecodeEncodeException: If there is no decoding class defined for the PGN or, in the case
    of a proprietary PGN, no decoding class is available for the specific manufacturer ID.
    """
    try:
        n2k_obj_class = nmea2k_generated_classes[msg.pgn]
    except KeyError:
        # _logger.error(f"No decoding class defined for PGN {msg.pgn}")
        raise N2KMissingDecodeEncodeException

    if PGNDef.is_pgn_proprietary(msg.pgn) and isinstance(n2k_obj_class, dict):
        # find the actual class for the manufacturer
        mfg_id = msg.get_manufacturer()
        try:
            n2k_obj_class = n2k_obj_class[mfg_id]
        except KeyError:
            _logger.error(f"No decoding class for PGN {msg.pgn} manufacturer id {mfg_id}")
            raise N2KMissingDecodeEncodeException

    # we have the class, so we can build the object
    return n2k_obj_class(message=msg)


def get_n2k_object_from_protobuf(protobuf: nmea2000_decoded_pb):
    """
    Converts a Protocol Buffer object to its corresponding NMEA 2000 object.

    Summary:
    This function takes a Protocol Buffer (protobuf) object, validates its type, and then
    maps it to a corresponding NMEA 2000 object using predefined classes. If no decode
    class is defined for the given PGN (Parameter Group Number) of the protobuf, an exception
    is raised. The function enforces strict type checking to avoid issues during runtime.

    Parameters:
    protobuf: nmea2000_decoded_pb
        A Protocol Buffer object representing NMEA 2000 data.

    Returns:
    n2k_obj_class
        An instance of the class representing the NMEA 2000 object, derived from the input
        Protocol Buffer object.

    Raises:
    TypeError
        If the input protobuf is not of type nmea2000_decoded_pb.
    N2KMissingDecodeEncodeException
        If no decoding class is defined for the PGN value of the input protobuf.
    """
    if not isinstance(protobuf, nmea2000_decoded_pb):
        # we must enforce type checking here => can lead to not understandable issues down the road
        _logger.critical("get_n2k_object_from_protobuf type mismatch. Expecting nmea2000_decoded_pb, got %s" % type(protobuf))
        raise TypeError("get_n2k_object_from_protobuf type mismatch. Expecting nmea2000_decoded_pb, got %s" % type(protobuf))
    try:
        n2k_obj_class = nmea2k_generated_classes[protobuf.pgn]
    except KeyError:
        _logger.error(f"No decoding class defined for PGN {protobuf.pgn}")
        raise N2KMissingDecodeEncodeException

    return n2k_obj_class(protobuf=protobuf)






