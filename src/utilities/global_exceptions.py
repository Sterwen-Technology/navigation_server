# -------------------------------------------------------------------------------
# Name:        global exceptions across the application
# Purpose:
#
# Author:      Laurent Carré
#
# Created:     02/10/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2022
# Licence:     Eclipse Public License 2.0
# -------------------------------------------------------------------------------


class ObjectCreationError(Exception):
    pass


class N2KDecodeException(Exception):
    pass


class N2KDecodeEOLException(N2KDecodeException):
    pass


class N2KMissingEnumKeyException(N2KDecodeException):
    pass


class N2KUnknownPGN(Exception):
    pass


class N2KDefinitionError(Exception):
    pass


class N2KEncodeException(Exception):
    pass
