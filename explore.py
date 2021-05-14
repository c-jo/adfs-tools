#! /usr/bin/python

from datetime import datetime
from utils import get_map
from objects import BigDir
import sys

if len(sys.argv) != 2:
    print("Usage: explore <device>")
    exit(1)

fd = open(sys.argv[1], "rb")
fs_map = get_map(fd)

root_fragment  = fs_map.disc_record.root >> 8
root_locations = fs_map.find_fragment(root_fragment, fs_map.disc_record.root_size)

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
        path_str += item.name

    cmd = raw_input(path_str+"> ").split()

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

    if cmd[0] == 'quit' or cmd[0] == 'exit':
        quit = True

