#
#  Script to adjust grpc generated files
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
    i_grpc = filename.find('_grpc')
    module_name = filename[:i_grpc]
    output_filename = os.path.join(rel_dir, "tmpFile")
    of = open(output_filename, "w")
    with open(full_filename, "r") as input_f:
        for line in input_f:
            if line.startswith('import'):
                start = line.find(module_name)
                if start != -1:
                    head = line[:start-1]
                    tail = line[start+len(module_name)+1:]
                    output_l = "%s %s.%s %s\n" % (head, prefix, module_name, tail)
                    # print(output_l)
                    of.write(output_l)
                    continue
            of.write(line)
    of.close()
    os.remove(full_filename)
    os.rename(output_filename, full_filename)


if __name__ == '__main__':
    main()

