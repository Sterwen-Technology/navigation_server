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


class ConfigurationException(Exception):
    pass


class ObjectFatalError(Exception):
    pass


class N2KDecodeException(Exception):
    pass


class N2KInvalidMessageException(Exception):
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


class IncompleteMessage(Exception):
    pass


class SocketCanError(Exception):

    def __init__(self, message, can_error: int = 0) -> None:
        super().__init__(message)
        self._can_error = can_error

    @property
    def can_error(self) -> int:
        return self._can_error
