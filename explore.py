#! /usr/bin/python

from utils import get_map, DiscImage, HDFImage
from objects import BigDir, BootBlock, BOOT_BLOCK_ADDRESS
import sys
import cmd
import os

if len(sys.argv) != 2:
    print("Usage: explore <device>")
    exit(1)

if os.path.splitext(sys.argv[1])[1] == '.hdf':
    disc = HDFImage(open(sys.argv[1], "rb"))
else:
    disc = DiscImage(open(sys.argv[1], "rb"))
bb = BootBlock.from_buffer_copy(disc.read_at(BOOT_BLOCK_ADDRESS, 0x200))

fs_map = get_map(disc)
# fs_map.disc_record.show()

root_fragment  = fs_map.disc_record.root >> 8
root_locations = fs_map.find_fragment(root_fragment, fs_map.disc_record.root_size)

root = BigDir(disc.read_at((root_locations[0])[0], fs_map.disc_record.root_size))

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
        csd = BigDir(disc.read_at(location[0], dirent.length))
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

