#-------------------------------------------------------------------------------
# Name:        mmcli_interface.py
# Purpose:     provide an interface to mmcli to manage modems
#              That shall replace the existing ad-hoc quectel_modem Python library
# Author:      Laurent Carré
#
# Created:     23/03/2025
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import json
import subprocess
import sys

_logger = logging.getLogger('ShipDataServer.' + __name__)

def mmcli_request(command: list) -> dict:
    args = ['mmcli', '-J'] + command
    result = subprocess.run(args, capture_output=True, encoding="utf-8")
    if result.returncode == 0:
        return json.loads(result.stdout)
    else:
        _logger.error(result.stderr)
        return None

class ModemControl:

    def __init__(self):
        self._modems = []

    def detect(self):
        result = mmcli_request(['-L'])
        modems = result['modem-list']

        for modem in modems:
            # print(modem)
            modem_no = modem[-1]
            print("Found modem:", modem)
            modem_dict = mmcli_request(['-m', modem_no])
            json.dump(modem_dict['modem']['generic'], sys.stdout, indent=2)
            print()
            # print(modem_dict['modem']['generic'].keys())
            self._modems.append(Modem(modem_no, modem_dict['modem']['generic']))

    def get_modem(self, modem_no):
        return self._modems[modem_no]

    def nb_modems(self) -> int:
        return len(self._modems)


class Modem:

    def __init__(self, modem_index, properties: dict):
        self._modem_index = modem_index
        self._properties = properties
        self._inserted_sims = []
        for sim in self.sim_slots:
            if sim == "/":
                break
            sim_no = sim[-1]
            print("Querying SIM", sim_no)
            sim = mmcli_request(['-i', sim_no])
            print (sim)
            self._inserted_sims.append(SIM(sim_no, sim['sim']['properties']))
        if len(self._inserted_sims) > 0:
            self._active_sim = self._inserted_sims[int(self.sim[-1])]
        else:
            self._active_sim = None


    @property
    def active_sim(self):
        return self._active_sim

    def __getattr__(self, item):
        underscore = item.find('_')
        if underscore > 2:
            item = item.replace('_', '-')
        try:
            return self._properties[item]
        except KeyError:
            raise AttributeError

class SIM:

    def __init__(self, sim_no, properties):
        self._sim_no = sim_no
        self._properties = properties

    def __getattr__(self, item):
        try:
            return self._properties[item]
        except KeyError:
            raise AttributeError



if __name__ == "__main__":
    modem_control = ModemControl()
    modem_control.detect()
    if modem_control.nb_modems() > 0:
        modem = modem_control.get_modem(0)
        print(modem.manufacturer, modem.model)
        if modem.active_sim is not None:
            print("IMSI=", modem.active_sim.imsi)
