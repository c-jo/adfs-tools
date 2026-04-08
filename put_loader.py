#! /usr/bin/python

import sys
import struct
from utils import get_map
from device import DiscImage

DOS_MAX = 128*1024*1024

if len(sys.argv) != 3:
    print("Usage: put_loader <device> <loader file>")
    exit(1)

fd = open(sys.argv[2], "rb")
dos_data = fd.read(DOS_MAX)
fd.close()

print("DOS area is {0} bytes.".format(len(dos_data)))

disc = DiscImage(open(sys.argv[1], "r+b"))

fs_map = get_map(disc)
lfau = fs_map.disc_record.bpmb
min_frag = (fs_map.disc_record.idlen+1)*fs_map.disc_record.bpmb

dos_start = min_frag // fs_map.disc_record.secsize
dos_secs  = len(dos_data) // fs_map.disc_record.secsize

print("Disc has LFAU of {}, minium fragment size {}K.".format(lfau,min_frag//1024))
print("Loader area starts at sector {}".format(dos_start))

disc_size = disc.size()

adfs_start = dos_start+dos_secs+1
adfs_secs  = disc_size // fs_map.disc_record.secsize - dos_secs

chs_dummy = ( 254, 255, 255 )
part_table = disc.read_at(0, 512)

p1 = part_table[0x1be:0x1be+16]
p2 = part_table[0x1ce:0x1ce+16]
p3 = part_table[0x1de:0x1de+16]
p4 = part_table[0x1ee:0x1ee+16]

p1_data = struct.unpack("BBBBBBBBII",p1)
p4_data = struct.unpack("BBBBBBBBII",p4)

p1_new = struct.pack("BBBBBBBBII", 0x80,\
    chs_dummy[0],chs_dummy[1],chs_dummy[2], 11,
    chs_dummy[0],chs_dummy[1],chs_dummy[2],
    dos_start, dos_secs)

p2_new = struct.pack("BBBBBBBBII", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0 )
p3_new = struct.pack("BBBBBBBBII", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0 )

p4_new = struct.pack("BBBBBBBBII", 0x00,\
    chs_dummy[0],chs_dummy[1],chs_dummy[2], 0xad,
    chs_dummy[0],chs_dummy[1],chs_dummy[2],
    adfs_start, adfs_secs)

new_part = part_table[0:0x1be] + p1_new + p2_new + p3_new + p4_new + b"\x55\xaa"

disc.write_at(0, new_part)
disc.write_at(dos_start * fs_map.disc_record.secsize, dos_data)
