#-------------------------------------------------------------------------------
# Name:        navigation_uuid
# Purpose:     utilities for uuid
#
# Author:      Laurent Carré
#
# Created:     12/08/2025
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import uuid

from navigation_server.generated.uuid_pb2 import ObjectId


def fill_uuid_protobuf(uuid_pb: ObjectId, uuid_value: uuid.UUID):
    # for simplicity we use string variant
    uuid_pb.urn = uuid_value.urn