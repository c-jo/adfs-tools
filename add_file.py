#! /usr/bin/python

from objects import BigDir
from utils import get_map

fd = open("/dev/mmcblk0", "r+b")

fs_map = get_map(fd)

root_frag_id    = fs_map.disc_record.root >> 8
root_sec_offset = fs_map.disc_record.root & 0xff

root_locations = fs_map.find_fragment(root_frag_id, fs_map.disc_record.root_size)

fd.seek((root_locations[0])[0])

root = BigDir(fd.read(fs_map.disc_record.root_size))
root.delete('Loader')
root.add('Loader', 0xffffc856, 0xeadfc18c, 50331648, 3, 0x300)
root.sequence += 1
root.show()
root.data()

fd.seek((root_locations[0])[0])
fd.write(root.data())
