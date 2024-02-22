#! /usr/bin/python

from datetime import datetime
from utils import get_map
from objects import BigDir, BootBlock
import sys
import cmd

if len(sys.argv) != 2:
    print("Usage: explore <device>")
    exit(1)

fd = open(sys.argv[1], "rb")
fd.seek(0xc00)
bb = BootBlock.from_buffer_copy(fd.read(0x200))
fd.seek(0)

fs_map = get_map(fd)
# fs_map.disc_record.show()

root_fragment  = fs_map.disc_record.root >> 8
root_locations = fs_map.find_fragment(root_fragment, fs_map.disc_record.root_size)

fd.seek((root_locations[0])[0])

root = BigDir(fd.read(fs_map.disc_record.root_size))

csd = root
path = [root]

csd.show()

class Shell(cmd.Cmd):
    intro = ''
    prompt = '$> '

    def do_dir(self, arg):
        'Change into the specified directory.'
        global csd
        dirent = csd.find(arg.encode('latin-1'))
        if not dirent:
            print("Not found.")
            return
        if not dirent.is_directory():
            print("Not a directory.")
            return

        location = fs_map.find_fragment(dirent.ind_disc_addr >> 8, dirent.length)[0]
        fd.seek(location[0])

        csd = BigDir(fd.read(dirent.length))
        path.append(csd)

    def do_up(self, arg):
        'Change into the parent directory.'
        global csd
        global path
        if len(path) > 1:
            path = path[:-1]
            csd = path[-1]

    def do_cat(self, arg):
        'List the contents of the current directory'
        csd.show()

    def do_zone(self, arg):
        'Show info about a zone'
        zone = int(arg)
        print("Zone: {} - {} to {}".format(zone, *fs_map.zone_range(zone)))
        print("Header: {:02x} {:02x} {:02x} {:02x}".format(*fs_map.zone_header(zone)))
        fs_map.show_zone(zone, True)
        print("Zone check (calclated): {:02x}".format(fs_map.calc_zone_check(zone)))

    def do_quit(self, arg):
        'Exits the exploerer.'
        return True

    def do_EOF(self, arg):
        return True

    def postcmd(self, stop, line):
        path_str = ''
        for item in path:
            if path_str != '':
                path_str += '.'
            path_str += item.name.decode('latin-1')

        self.prompt = path_str + "> "
        return cmd.Cmd.postcmd(self, stop, line)


Shell().cmdloop()

