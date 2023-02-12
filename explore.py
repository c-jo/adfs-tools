#! /usr/bin/python

from datetime import datetime
from utils import get_map
from objects import BigDir, BootBlock
import sys

if len(sys.argv) != 2:
    print("Usage: explore <device>")
    exit(1)

fd = open(sys.argv[1], "rb")
fd.seek(0xc00)
bb = BootBlock.from_buffer_copy(fd.read(0x200))
fd.seek(0)

print(bb.checksum)
print(bb.calculate_checksum())

fs_map = get_map(fd)
fs_map.disc_record.show()
print(fs_map.cross_check())

# fs_map.show(False)

root_fragment  = fs_map.disc_record.root >> 8
root_locations = fs_map.find_fragment(root_fragment, fs_map.disc_record.root_size)

print("Root fragment: {:x} at {}".format(root_fragment,root_locations))

print(fs_map.disc_to_map(root_locations[0][0]))

fd.seek((root_locations[0])[0])

root = BigDir(fd.read(fs_map.disc_record.root_size))

csd = root
csd.show()

quit = False
path = [root]

while not quit:
    path_str = ''
    for item in path:
        if path_str != '':
            path_str += '.'
        path_str += item.name.decode('latin-1')

    cmd = input(path_str+"> ").split()

    if cmd[0] == 'cat' or cmd[0] == '.':
        csd.show()

    if cmd[0] == 'dir':
        dirent = csd.find(cmd[1])
        if not dirent:
            print("Not found.")
            continue
        if not dirent.is_directory():
            print("Not a directory.")
            continue

        location = fs_map.find_fragment(dirent.ind_disc_addr >> 8, dirent.length)[0]
        fd.seek(location[0])

        csd = BigDir(fd.read(dirent.length))
        path.append(csd)

    if cmd[0] == 'up':
        if len(path) > 1:
            path = path[:-1]
            csd = path[-1]


    if cmd[0] == 'map':
        with open("mapdump","wb") as f:
            f.write(fs_map.data)
        fs_map.show(False)

    if cmd[0] == 'zone':
        zone = int(cmd[1])
        print("Zone: {} {} to {}".format(zone, *fs_map.zone_range(zone)))
        print("{:02x} {:02x} {:02x} {:02x}".format(*fs_map.zone_header(zone)))
        fs_map.show_zone(zone, True)
        print("Zone check (calclated): {:02x}".format(fs_map.calc_zone_check(zone)))


    if cmd[0] == 'quit' or cmd[0] == 'exit':
        quit = True

