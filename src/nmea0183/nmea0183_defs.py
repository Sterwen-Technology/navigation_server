#-------------------------------------------------------------------------------
# Name:        NMEA0183 DEFS
# Purpose:     Manages all NMEA0183 definitions
#
# Author:      Laurent Carré
#
# Created:     29/07/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging

from router_common.xml_utilities import XMLDefinitionFile, XMLDecodeError

_logger = logging.getLogger("ShipDataServer"+"."+__name__)


class NMEA0183Definitions(XMLDefinitionFile):

    nmea0183_sentences_defs = None

    @staticmethod
    def get_nmea0183_defs():
        return NMEA0183Definitions.nmea0183_sentences_defs

    def __init__(self, xml_file):

        super().__init__(xml_file, "N0183Defns")
        self._nmea_defs = {}

        for xml_def in self._definitions.iterfind("N0183Defn"):
            sentence_def = NMEA0183SentenceDef(xml_def)
            print("Found sentence:", sentence_def.code)
            self._nmea_defs[sentence_def.code] = sentence_def
        self.nmea0183_sentences_defs = self

    def sentences(self):
        return self._nmea_defs.values()




class NMEA0183SentenceDef:

    def __init__(self, xml_def):

        self._code = xml_def.attrib['Code']
        self._description = xml_def.attrib['Description']
        self._fields = []
        fields = xml_def.find('Fields')
        for field in fields.iter():
            # print(field.tag)
            if field.tag == 'Fields':
                continue
            if field.tag.endswith('Field'):
                try:
                    self._fields.append(NMEA0183Field(field))
                except ValueError:
                    print("Error in Sentence Code", self._code, field.attrib['Name'])

    @property
    def code(self):
        return self._code

    def check_field_indexes(self):
        i = 0
        for f in self._fields:
            if f.index != i:
                print("Sentence", self._code, "Error in field index", i, "!=", f.index)
            i += 1


class NMEA0183Field:

    def __init__(self, xml_field):
        self._type = xml_field.tag
        self._name = xml_field.attrib['Name']
        descr = xml_field.find('Description')
        if descr is None:
            raise ValueError
        self._description = descr.text
        index = xml_field.find('SegmentIndex')
        if index is None:
            raise ValueError
        self._index = int(index.text)

    @property
    def index(self):
        return self._index


def main():
    tree = NMEA0183Definitions("../../def/N0183Defns.N0183Dfn.xml")
    for s in tree.sentences():
        s.check_field_indexes()


if __name__ == '__main__':
    main()

