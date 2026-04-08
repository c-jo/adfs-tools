#! /usr/bin/python

from utils import get_map
from device import DiscImage
from objects import BigDir
import sys

if len(sys.argv) != 2:
    print("Usage: walk <device>")
    exit(1)

def split_internal_disc_address(internal_disc_address):
    sector_offset = internal_disc_address & 0xff
    fragment_id   = internal_disc_address >> 8
    return (fragment_id, sector_offset)

def walk(directory, parent="$"):
    print("{}.{}".format(parent, directory.name.decode('latin-1')))
    for entry in directory.entries:
        if entry.attribs & 1<<3:
            frag_id, offset = split_internal_disc_address(entry.ind_disc_addr)

            if offset > 0:
                offset = (offset-1) * fs_map.disc_record.secsize

            if offset > 0:
                raise RuntimeError("Directory has sector offset > 0")

            locations = fs_map.find_fragment(frag_id, entry.length)
            data = None
            for start,end in locations:
                frag_data = disc.read_at(start, end-start)
                if data:
                    data += frag_data
                else:
                    data = frag_data

            data = data[:entry.length]

            walk(BigDir(data), parent+'.'+entry.name.decode('latin-1'))

disc = DiscImage(sys.argv[1], 'rb')
fs_map = get_map(disc)

root_frag_id    = fs_map.disc_record.root >> 8
root_sec_offset = fs_map.disc_record.root &  0xff

root_locations = fs_map.find_fragment(root_frag_id, fs_map.disc_record.root_size)

root = BigDir(disc.read_at((root_locations[0])[0], fs_map.disc_record.root_size))
walk(root)

