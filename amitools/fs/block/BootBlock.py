import os.path
from Block import Block

class BootBlock(Block):
  # raw dos types
  DOS0 = 0x444f5300
  DOS1 = 0x444f5301
  DOS2 = 0x444f5302
  DOS3 = 0x444f5303
  DOS4 = 0x444f5304
  DOS5 = 0x444f5305
  # more convenient dos type
  DOS_OFS = DOS0
  DOS_FFS = DOS1
  DOS_OFS_INTL = DOS2
  DOS_FFS_INTL = DOS3
  DOS_OFS_INTL_DIRCACHE = DOS4
  DOS_FFS_INTL_DIRCACHE = DOS5
  # string names for dos types
  dos_type_names = [
      'ofs',
      'ffs',
      'ofs+intl',
      'ffs+intl',
      'ofs+intl+dircache',
      'ffs+intl+dircache',
      'N/A',
      'N/A'
  ]
  
  DOS_MASK_FFS = 1
  DOS_MASK_INTL = 2
  DOS_MASK_DIRCACHE = 4
  
  def __init__(self, blkdev, blk_num=0):
    Block.__init__(self, blkdev, blk_num)
    self.dos_type = None
    self.got_root_blk = None
    self.got_chksum = 0
    self.calc_chksum = 0
    self.boot_code = None
    self.num_extra = self.blkdev.bootblocks - 1
    self.max_boot_code = self.blkdev.bootblocks * self.blkdev.block_bytes - 12
    self.extra_blks = []
  
  def create(self, dos_type=DOS0, root_blk=None, boot_code=None):
    Block.create(self)
    self._create_data()
    self.dos_type = dos_type    
    self.valid_dos_type = True
    # root blk
    self.calc_root_blk = int(self.blkdev.num_blocks / 2)
    if root_blk != None:
      self.got_root_blk = root_blk
    else:
      self.got_root_blk = self.calc_root_blk      
    # create extra blks
    self.extra_blks = []
    for i in xrange(self.num_extra):
      b = Block(self.blkdev, self.blk_num + 1 + i)
      b.create()
      self.extra_blks.append(b)
    # setup boot code
    self.set_boot_code(boot_code)
  
  def set_boot_code(self, boot_code):
    if boot_code != None:
      if len(boot_code) <= self.max_boot_code:
        self.boot_code = boot_code
        self.valid = True
      else:
        self.valid = False
    else:
      self.boot_code = None
      self.valid = True   
    return self.valid
  
  def _calc_chksum(self):
    all_blks = [self] + self.extra_blks
    n = self.blkdev.block_longs
    chksum = 0
    for blk in all_blks:
      for i in xrange(n):
        if i != 1: # skip chksum
          chksum += blk._get_long(i)
          if chksum > 0xffffffff:
            chksum += 1
            chksum &= 0xffffffff
    return (~chksum) & 0xffffffff
  
  def read(self):
    self._read_data()
    # read extra boot blocks
    self.extra_blks = []
    for i in xrange(self.num_extra):
      b = Block(self.blkdev, self.blk_num + 1 + i)
      b._read_data()
      self.extra_blks.append(b)
      
    self.dos_type = self._get_long(0)
    self.got_chksum = self._get_long(1)
    self.got_root_blk = self._get_long(2)
    self.calc_chksum = self._calc_chksum()
    # calc position of root block
    self.calc_root_blk = int(self.blkdev.num_blocks / 2)
    # check validity
    self.valid_chksum = self.got_chksum == self.calc_chksum
    self.valid_dos_type = (self.dos_type >= self.DOS0) and (self.dos_type <= self.DOS5)
    self.valid = self.valid_dos_type

    # look for boot_code
    if self.valid:
      self.read_boot_code()
    return self.valid
  
  def read_boot_code(self):
    boot_code = self.data[12:]
    for blk in self.extra_blks:
      boot_code += blk.data.raw
    # remove nulls at end
    pos = len(boot_code) - 1
    while pos > 0:
      if ord(boot_code[pos])!=0:
        pos += 1
        break
      pos -= 1
    pos = (pos + 1) & ~1 # word align
    # something left
    if pos > 0:
      boot_code = boot_code[:pos]
      self.boot_code = boot_code
  
  def write(self):
    self._create_data()
    self._put_long(0, self.dos_type)
    self._put_long(2, self.got_root_blk)

    if self.boot_code != None:
      self.write_boot_code()
      self.calc_chksum = self._calc_chksum()
      self._put_long(1, self.calc_chksum)
      self.valid_chksum = True
    else:
      self.calc_chksum = 0
      self.valid_chksum = False

    self._write_data()
  
  def write_boot_code(self):
    n = len(self.boot_code)
    bb = self.blkdev.block_bytes
    first_size = bb - 12
    boot_code = self.boot_code
    # spans more blocks
    if n > first_size:
      extra = boot_code[first_size:]
      boot_code = boot_code[:first_size]
      # write extra blocks
      pos = 0
      off = 0
      n -= first_size
      while n > 0:
        num = n
        if num > bb:
          num = bb
        self.extra_blks[pos].data[:num] = extra[off:off+num]
        self.extra_blks[pos]._write_data()
        off += num
        pos += 1
        n -= num
      # use this for first block
      n = first_size
        
    # embed boot code and calc correct chksum
    self.data[12:12+n] = boot_code
    
  def get_dos_type_flags(self):
    return self.dos_type & 0x7
  
  def get_dos_type_str(self):
    return self.dos_type_names[self.get_dos_type_flags()]
    
  def is_ffs(self):
    t = self.get_dos_type_flags()
    return (t & self.DOS_MASK_FFS) == self.DOS_MASK_FFS
  
  def is_intl(self):
    t = self.get_dos_type_flags()
    return self.is_dircache() or (t & self.DOS_MASK_INTL) == self.DOS_MASK_INTL
  
  def is_dircache(self):
    t = self.get_dos_type_flags()
    return (t & self.DOS_MASK_DIRCACHE) == self.DOS_MASK_DIRCACHE
  
  def dump(self):
    print "BootBlock(%d):" % self.blk_num
    print " dos_type:  0x%08x %s (valid: %s) is_ffs=%s is_intl=%s is_dircache=%s" \
      % (self.dos_type, self.get_dos_type_str(), self.valid_dos_type, self.is_ffs(), self.is_intl(), self.is_dircache())
    print " root_blk:  %d (got %d)" % (self.calc_root_blk, self.got_root_blk)
    print " chksum:    0x%08x (got) 0x%08x (calc)" % (self.got_chksum, self.calc_chksum)
    print " valid:     %s" % self.valid
    if self.boot_code != None:
        print " boot_code: %d bytes" % len(self.boot_code)

  def get_boot_code_dir(self):
    my_dir = os.path.dirname(__file__)
    bc_dir = os.path.join(my_dir, "bootcode")
    if os.path.exists(bc_dir):
      return bc_dir
    else:
      return None

    