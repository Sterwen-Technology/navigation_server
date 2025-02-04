#-------------------------------------------------------------------------------
# Name:        mod_pb2.py
# Purpose:     Script to adjust grpc generated files
#
# Author:      Laurent Carré
#
# Created:     25/10/2021
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------
#
#  arg1 = file to be analyzed and modified
#  arg2 = prefix to be added
#
import sys
import os


def main():
    full_filename = sys.argv[1]
    if not os.path.exists(full_filename):
        print(sys.argv[0], "File does not exists", full_filename)
        return
    rel_dir, filename = os.path.split(full_filename)
    print(sys.argv[0], "processing file", full_filename)
    prefix = sys.argv[2]
    keywords = []
    if len(sys.argv) > 3:
        for k in sys.argv[3:]:
            keywords.append(k+"_pb2")
    else:
        i_grpc = filename.find('_grpc')
        keywords.append(filename[:i_grpc])
    # print(full_filename, keywords)
    output_filename = os.path.join(rel_dir, "tmpFile")
    of = open(output_filename, "w")
    with open(full_filename, "r") as input_f:
        for line in input_f:
            if line.startswith('import'):
                for k in keywords:
                    start = line.find(k)
                    if start != -1: break
                # print("==>", line, k, start)
                if start != -1:
                    head = line[:start-1]
                    tail = line[start+len(k)+1:]
                    output_l = "%s %s.%s %s\n" % (head, prefix, k, tail)
                    # print(output_l)
                    of.write(output_l)
                    continue
            of.write(line)
    of.close()
    os.remove(full_filename)
    os.rename(output_filename, full_filename)


if __name__ == '__main__':
    main()

