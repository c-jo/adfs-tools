import struct
import array

def dir_check_words(data, count, dircheck):
    for word in struct.unpack("{0}I".format(count), data):
        dircheck = word ^ ( ((dircheck >> 13) & 0xffffffff) | ((dircheck << 19) & 0xffffffff) )
    return dircheck

def dir_check_bytes(data, count, dircheck):
    for byte in struct.unpack("{0}B".format(count), data):
        dircheck = byte ^ ( ((dircheck >> 13) & 0xffffffff) | ((dircheck << 19) & 0xffffffff) )
    return dircheck

class DiscRecord(object):
    def __init__(self, data):
        self.log2secsize, self.secspertrack, self.heads, self.density, \
        self.idlen, self.log2bpmb, self.skew, self.bootoption, self.lowsector, \
        nzones_1, self.zone_spare, self.root, disc_size_1, self.disc_id, \
        self.disc_name, self.disc_type, disc_size_2, self.log2share_size, \
        self.big_flag, nzones_2, self.format_version, self.root_size \
            = struct.unpack('BBBBBBBBBBHIIH10sIIBBBxII8x', data)

        self.nzones    = (nzones_2 << 8) + nzones_1
        self.disc_size = (disc_size_2<<32) + disc_size_1
        self.secsize   = 1<<self.log2secsize
        self.bpmb      = 1<<self.log2bpmb

    def show(self):
        print("Disc Record")
        print("Sector size: %d" %self.secsize)
        print("ID Length: %d" % self.idlen)
        print("Bytes per map bit: %d" % self.bpmb)
        print("Number of zones: %d" % self.nzones)
        print("Zone spare: %d" % self.zone_spare)
        print("Disc Size: %d (M)" % (self.disc_size / 1024 / 1024) )
        print("Root size: %d\n" % self.root_size)

class Map(object):
    def __init__(self, data):
        self.data = array.array('B')
        self.data.fromstring(data)
        self.disc_record = DiscRecord(data[4:64])
        self.nzones = self.disc_record.nzones
        self.id_per_zone = ((self.disc_record.secsize*8) - self.disc_record.zone_spare) / (self.disc_record.idlen+1)

    def show(self, unused=True):
        for zone in range(self.nzones):
            self.show_zone(zone,unused)


    def zone_range(self, zone):
        return (\
             ((self.disc_record.secsize*8-self.disc_record.zone_spare)*zone)  - (480 if zone > 0 else 0),
             ((self.disc_record.secsize*8-self.disc_record.zone_spare)*(zone+1)) - 480 - 1)

    def get_bit(self, zone, bit):
        byte = (bit / 8) + (64 if zone == 0 else 4) # Zone 0 has the disc record
	shift = bit % 8
	data = self.data[byte+zone*self.disc_record.secsize]
	val = data & 1 << shift
	return 1 if val > 0 else 0

    def set_bit(self, zone, bit, val):
        byte = (bit / 8) + (64 if zone == 0 else 4) # Zone 0 has the disc record
	shift = bit % 8
	old_data = self.data[byte+zone*self.disc_record.secsize]
        new_data = old_data & ( 0xff ^ 1<<shift) | ((1<<shift) if val else 0)
        self.data[byte+zone*self.disc_record.secsize] = new_data

    def calc_zone_check(self, zone):
        sum_vector0 = 0
        sum_vector1 = 0
        sum_vector2 = 0
        sum_vector3 = 0
        zone_start  = zone * self.disc_record.secsize

        rover = ((zone+1)*self.disc_record.secsize)-4
        while rover > zone_start:
            sum_vector0 += self.data[rover+0] + (sum_vector3>>8)
            sum_vector3 &= 0xff
            sum_vector1 += self.data[rover+1] + (sum_vector0>>8)
            sum_vector0 &= 0xff
            sum_vector2 += self.data[rover+2] + (sum_vector1>>8)
            sum_vector1 &= 0xff
            sum_vector3 += self.data[rover+3] + (sum_vector2>>8)
            sum_vector2 &= 0xff
            rover -= 4

        # Don't add the check byte when calculating its value
	sum_vector0 += (sum_vector3>>8)
	sum_vector1 += self.data[rover+1] + (sum_vector0>>8)
	sum_vector2 += self.data[rover+2] + (sum_vector1>>8)
	sum_vector3 += self.data[rover+3] + (sum_vector2>>8)
	
        return (sum_vector0^sum_vector1^sum_vector2^sum_vector3) & 0xff;

    def allocate(self, zone, frag_id, from_bit, to_bit):
        bit = from_bit
        for i in range(self.disc_record.idlen):
           self.set_bit(zone, bit, frag_id & (1<<i))
           bit += 1

        while bit < to_bit:
           self.set_bit(zone, bit, 0)
           bit += 1

        self.set_bit(zone, bit, 1)

        bits_before = ((self.disc_record.secsize*8-self.disc_record.zone_spare)*zone) - (480 if zone > 0 else 0)
        last_bit    = ((self.disc_record.secsize*8-self.disc_record.zone_spare)*(zone+1)) -480

        if bit < (last_bit-bits_before-1):
           new_free_link = 0x8001 + bit + (63*8 if zone == 0 else 3*8)
        else:
           new_free_link = 0x8000

        self.data[zone * self.disc_record.secsize+1] = (new_free_link >> 0) & 0xff
        self.data[zone * self.disc_record.secsize+2] = (new_free_link >> 8) & 0xff
        self.data[zone * self.disc_record.secsize+0] = self.calc_zone_check(zone)

    def show_zone(self, zone, show_unused):
        zone_start  = zone * self.disc_record.secsize
        bits_before = ((self.disc_record.secsize*8-self.disc_record.zone_spare)*zone) - (480 if zone > 0 else 0)
        last_bit    = ((self.disc_record.secsize*8-self.disc_record.zone_spare)*(zone+1)) -480
        free_link   = (self.data[zone_start+2])*256+(self.data[zone_start+1])

        if free_link == 0x8000:
            free_offset = None

        else:
            free_offset = (free_link & 0x7fff) - (63*8 if zone == 0 else 3*8)

        if free_offset is not None and free_offset == 0 and not show_unused:
            return

        if free_offset:
            print("Zone %d (FreeLink = %x - %d bits)" % (zone, free_link, free_offset))
        else:
            print("Zone %d (FreeLink = %x - No free space)" % (zone, free_link))
            
        bit = 0
        while True:
           frag_id = 0
           start   = bit

           for i in range(self.disc_record.idlen):
              frag_id |= self.get_bit(zone, bit) << i
              bit += 1

           while (self.get_bit(zone, bit) == 0):
               if bit > last_bit:
                   print "** Stop bit not found before end of zone."
                   break
               bit += 1
       
           bit += 1
           disc_start = (start+bits_before)*self.disc_record.bpmb
           disc_end   = (bit  +bits_before)*self.disc_record.bpmb

           print("  Fragment ID: %x (bits %d to %d) [disc %x to %x (%d)]" %
               (frag_id, start, bit, disc_start, disc_end, disc_end-disc_start))

           if bit+bits_before >= last_bit:
               break

    def find_in_zone(self, search_id, zone):
        zone_start  = zone * self.disc_record.secsize
        bits_before = ((self.disc_record.secsize*8-self.disc_record.zone_spare)*zone) - (480 if zone > 0 else 0)
        free_link =    (self.data[zone_start+2])*256+(self.data[zone_start+1])

        rv = []

        bit = 0
        while True:
           frag_id = 0
           start   = bit

           for i in range(self.disc_record.idlen):
              frag_id |= self.get_bit(zone, bit) << i
              bit += 1

           while (self.get_bit(zone, bit) == 0):
               bit += 1
       
           bit += 1
           disc_start = (start+bits_before)*self.disc_record.bpmb
           disc_end   = (bit  +bits_before)*self.disc_record.bpmb

           if frag_id == search_id:
               rv.append((disc_start, disc_end))

           if bit+bits_before >= ((self.disc_record.secsize*8-self.disc_record.zone_spare)*(zone+1)) -480:
               break

        return rv

    def find_fragment(self, fragment_id, length = None):
        addresses = [] # List of (start,end) disc addresses

        start_zone = fragment_id / self.id_per_zone
        zone = start_zone

        while True:
           in_this = self.find_in_zone(fragment_id, zone)
           if len(in_this) > 0:
               addresses += in_this

           if length:
              count = 0
              for (start,end) in addresses:
                  count += end-start

              if count >= length:
                  break  

           zone += 1

           if zone >= self.disc_record.nzones:
               zone = 0

           if zone == start_zone:
               break

        return addresses

class BigDir(object):
    class Entry(object):
        def __init__(self, name, loadaddr, execaddr, length, attribs, ind_disc_addr):
            self.name     = name
            self.loadaddr = loadaddr
            self.execaddr = execaddr
            self.length   = length
            self.attribs  = attribs
            self.ind_disc_addr = ind_disc_addr

        @staticmethod
        def from_dir(data, name_heap):
            loadaddr, execaddr, length, ind_disc_addr, attribs,\
            name_len, name_ptr = struct.unpack("IIIIIII",data)
            name = name_heap[name_ptr:name_ptr+name_len]
            return BigDir.Entry(name, loadaddr, execaddr, length, attribs, ind_disc_addr)

        def attr_str(self):
            s = ''
            s += "R" if self.attribs & 1<<0 else "-"
            s += "W" if self.attribs & 1<<1 else "-"
            s += "L" if self.attribs & 1<<2 else "-"
            s += "D" if self.attribs & 1<<3 else "-"
            s += "r" if self.attribs & 1<<4 else "-"
            s += "w" if self.attribs & 1<<5 else "-"
            return s

        def show(self):
            print '{0:<15} {1:08x} {2:08x} {3:12} {4} {5:x}'.format(\
                   self.name, self.loadaddr, self.execaddr, self.length,
                   self.attr_str(), self.ind_disc_addr)
        
    def __init__(self, data):
        self.sequence, sbpr, name_len, self.size, \
        entries, names_size, self.parent_id = struct.unpack("Bxxx4sIIIII",data[0:0x1c])

        if sbpr != 'SBPr':
            raise RuntimeError("Invalid directory start marker ({0})".format(sbpr))
        
        self.name = data[0x1c:0x1c+name_len]

        heap_start = (entries*0x1c) + ((0x1c+name_len+4)/4)*4
        heap_end   = heap_start+names_size
        heap_data  = data[heap_start:heap_end]

        self.entries = []
        data_start = ((0x1C+name_len+4)/4)*4

        for entry in range(0,entries):
            start = data_start + (entry*0x1C)
            self.entries.append(\
                BigDir.Entry.from_dir(data[start:start+0x1c], heap_data))

        oven, end_seq, check = struct.unpack("4sBxxB",data[-8:])
        
        if oven != 'oven':
            raise RuntimeError("Invalid directory end marker ({0})".format(oven))

        tail = data[-8:]
        calc = dir_check_words(data[0:heap_end], heap_end/4, 0)
        calc = dir_check_words(tail[0:4], 1, calc)
        calc = dir_check_bytes(tail[4:7], 3, calc)
        calc = (calc << 0 & 0xff) ^ (calc >> 8 & 0xff) ^ (calc >> 16 & 0xff) ^ (calc >> 24 & 0xff)

        if calc != check:
            raise RuntimeError("Directory check-byte failed.")

    def data(self):
        # TODO: Currently only handles 2048 byte directories.
        data = ''

        name_heap = ''
        heap_lookup = {}
        for entry in self.entries:
           heap_lookup[self.entries.index(entry)] = len(name_heap)
           name_heap += entry.name+'\x0d'

        # Word-justify it
        while len(name_heap) % 4 != 0:
            name_heap += '\x00'

        seq = self.sequence

        data = struct.pack('BBBB4sIIIII',seq,0,0,0,'SBPr',
            len(self.name),2048,len(self.entries),len(name_heap),self.parent_id)

        dir_name = self.name+'\x0d'
        while len(dir_name) % 4 != 0:
            dir_name += '\x00'

        data += dir_name

        for entry in self.entries:
            data += struct.pack("IIIIIII",
                               entry.loadaddr, entry.execaddr, entry.length,
                               entry.ind_disc_addr, entry.attribs,
                               len(entry.name),
                               heap_lookup[self.entries.index(entry)])

            #check = dir_check_words(data, 7, check)

        data += name_heap

        check = dir_check_words(data, len(data)/4, 0)

        tail = struct.pack('4sBBB','oven',seq,0,0)

        check = dir_check_words(tail[0:4], 1, check)
        check = dir_check_bytes(tail[4:7], 3, check)

        check = (check << 0 & 0xff) ^ (check >> 8 & 0xff) ^ (check >> 16 & 0xff) ^ (check >> 24 & 0xff)

        while len(data) < 2040:
            data += '\x00'

        data += tail + chr(check)	
        return data

    def show(self):
        print "Directory: {0} ({1})".format(self.name,self.sequence)
        for entry in self.entries:
            entry.show()

    def add(self, name, loadaddr, execaddr, length, attribs, ind_disc_addr):
        self.entries.append(BigDir.Entry(name, loadaddr, execaddr, length, attribs, ind_disc_addr))

    def __getitem__(self, name):
        for entry in self.entries:
            if entry.name == name:
                return entry

    def delete(self, name):
        for entry in self.entries:
            if entry.name == name:
                self.entries.remove(entry)
                return True


