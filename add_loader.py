#! /usr/bin/python

import sys
from objects import BigDir
from utils import get_map, DiscImage

if len(sys.argv) != 2:
    print("Usage: add_loader <device>")
    exit(1)

disc = DiscImage(open(sys.argv[1], "r+b"))

fs_map = get_map(disc)

root_frag_id    = fs_map.disc_record.root >> 8
root_sec_offset = fs_map.disc_record.root & 0xff

root_locations = fs_map.find_fragment(root_frag_id, fs_map.disc_record.root_size)

root = BigDir(disc.read_at((root_locations[0])[0], fs_map.disc_record.root_size))
root.delete('Loader')
root.add('Loader', 0xffffc856, 0xeadfc18c, 50331648, 3, 0x300)
root.sequence += 1
root.show()
root.data()

disc.write_at((root_locations[0])[0], root.data())
