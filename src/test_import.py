
import router_core
import nmea2000
import can_interface
import importlib
import sys
# import log_replay


def main():

    package_name = sys.argv[1]
    # print(sys.path)
    print(package_name)
    package = importlib.import_module(package_name)
    print(package)
    raw_log_coupler = getattr(package, 'RawLogCoupler')
    print(raw_log_coupler)


if __name__ == '__main__':
    main()
