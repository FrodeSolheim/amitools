#!/usr/bin/env python2.7
# romtool
#
# work with Amiga ROM files aka Kickstarts

from __future__ import print_function

import sys
import argparse
import os
import logging

from amitools.util.Logging import *
from amitools.util.HexDump import *
from amitools.rom.RomSplitter import *
from amitools.rom.RomBuilder import *
from amitools.rom.KickRom import *
from amitools.binfmt.hunk.BinFmtHunk import BinFmtHunk
from amitools.binfmt.BinFmt import BinFmt

desc="""romtool allows you to dissect, inspect, or create Amiga ROM files"""


def do_list_cmd(args):
  rs = RomSplitter()
  rs.list_roms(print, args.rom, show_entries=args.entries)
  return 0


def do_query_cmd(args):
  ri = args.rom_image
  rs = RomSplitter()
  if not rs.find_rom(ri):
    print(ri, "not found in split database!")
    return 100
  else:
    rs.print_rom(print)
    if args.module is None:
      e = rs.get_all_entries()
    else:
      e = rs.query_entries(args.module)
    rs.print_entries(print,e)
    return 0


def do_split_cmd(args):
  ri = args.rom_image
  rs = RomSplitter()
  rom = rs.find_rom(ri)
  if rom is None:
    logging.error(ri, "not found in split database!")
    return 100
  else:
    rs.print_rom(logging.info)
    # no output dir? end now
    out_path = args.output_dir
    if out_path is None:
      return 0
    # get modules to export
    if args.module is None:
      entries = rs.get_all_entries()
    else:
      entries = rs.query_entries(args.module)
    # setup output dir
    if not args.no_version_dir:
      out_path = os.path.join(out_path, rom.short_name)
    # make dirs
    if not os.path.isdir(out_path):
      logging.info("creating directory '%s'", out_path)
      os.makedirs(out_path)
    # create index file
    if not args.no_index:
      idx_path = os.path.join(out_path, "index.txt")
      logging.info("writing index to '%s'", idx_path)
      rs.write_index_file(idx_path)
    # extract entries
    bfh = BinFmtHunk()
    for e in entries:
      rs.print_entry(logging.info, e)
      bin_img = rs.extract_bin_img(e)
      out_file = os.path.join(out_path, e.name)
      logging.info("writing file '%s'", out_file)
      bfh.save_image(out_file, bin_img)
    return 0


def do_build_cmd(args):
  # get options
  rom_size = args.rom_size
  kick_addr = int(args.kick_addr, 16)
  ext_addr = int(args.ext_addr, 16)
  kickety_split = args.kickety_split
  rom_type = args.rom_type
  fill_byte = int(args.fill_byte, 16)
  rom_rev = args.rom_rev
  if rom_rev is not None:
    rom_rev = map(int, rom_rev.split("."))
  add_footer = args.add_footer
  # select rom builder
  if rom_type == 'kick':
    logging.info("building %d KiB Kick ROM @%08x", rom_size, kick_addr)
    rb = KickRomBuilder(rom_size,
                        base_addr=kick_addr, fill_byte=fill_byte,
                        kickety_split=kickety_split, rom_ver=rom_rev)
  elif rom_type == 'ext':
    logging.info("building %d KiB Ext ROM @%08x Rev %r for Kick @%08x",
                 rom_size, ext_addr, rom_rev, kick_addr)
    rb = ExtRomBuilder(rom_size,
                       base_addr=ext_addr, fill_byte=fill_byte,
                       add_footer=add_footer, rom_ver=rom_rev,
                       kick_addr=kick_addr)
  else:
    logging.error("Unknown rom_type=%s", rom_type)
    return 1
  # build file list
  file_list = rb.build_file_list(args.modules)
  # load modules
  bf = BinFmt()
  for f in file_list:
    # load image
    if not bf.is_image(f):
      logging.error("Can't load module '%s'", f)
      return 2
    name = os.path.basename(f)
    bin_img = bf.load_image(f)

    # handle kickety split
    if kickety_split and rb.cross_kickety_split(bin_img.get_size()):
      off = rb.get_current_offset()
      logging.info("@%08x: adding kickety split", off)
      rb.add_kickety_split()

    # add image
    off = rb.get_current_offset()
    logging.info("@%08x: adding module '%s'", off, f)
    e = rb.add_bin_img(name, bin_img)
    if e is None:
      logging.error("@%08x: can't add module '%s': %s", off, f, rb.get_error())
      return 3

  # build rom
  off = rb.get_current_offset()
  logging.info("@%08x: padding %d bytes with %02x", off, rb.get_bytes_left(), fill_byte)
  rom_data = rb.build_rom()
  if rom_data is None:
    logging.error("building ROM failed: %s", rb.get_error())

  # save rom
  output = args.output
  if output is not None:
    logging.info("saving ROM to '%s'", output)
    with open(output, "wb") as fh:
      fh.write(rom_data)
  return 0


def do_diff_cmd(args):
  # load ROMs
  img_a = args.image_a
  logging.info("loading ROM A from '%s'", img_a)
  rom_a = KickRom.Loader.load(img_a)
  img_b = args.image_b
  logging.info("loading ROM B from '%s'", img_b)
  rom_b = KickRom.Loader.load(img_b)
  # check sizes
  size_a = len(rom_a)
  size_b = len(rom_b)
  if not args.force and size_a != size_b:
    logging.error("ROM differ in size (%08x != %08x). Aborting", size_a, size_b)
    return 2
  # do diff
  base_addr = 0
  if args.rom_addr:
    base_addr = int(args.rom_addr, 16)
  elif args.show_address:
    kh = KickRom.Helper(rom_a)
    if kh.is_kick_rom():
      base_addr = kh.get_base_addr()
    else:
      logging.error("Not a KickROM! Can't detect base address.")
      return 3
  print_hex_diff(rom_a, rom_b, num=args.columns, show_same=args.same,
                 base_addr=base_addr)


def do_dump_cmd(args):
  img = args.image
  logging.info("loading ROM from '%s'", img)
  rom = KickRom.Loader.load(img)
  base_addr = 0
  if args.rom_addr:
    base_addr = int(args.rom_addr, 16)
  elif args.show_address:
    kh = KickRom.Helper(rom)
    if kh.is_kick_rom():
      base_addr = kh.get_base_addr()
    else:
      logging.error("Not a KickROM! Can't detect base address.")
      return 3
  print_hex(rom, num=args.columns, base_addr=base_addr)


def do_info_cmd(args):
  img = args.image
  rom = KickRom.Loader.load(img)
  kh = KickRom.KickRomAccess(rom)
  checks = [
    ('size', kh.check_size()),
    ('header', kh.check_header()),
    ('footer', kh.check_footer()),
    ('size_field', kh.check_size()),
    ('chk_sum', kh.verify_check_sum()),
    ('kickety_split', kh.check_kickety_split()),
    ('magic_reset', kh.check_magic_reset()),
    ('is_kick', kh.is_kick_rom())
  ]
  c = map(lambda x:"%-20s  %s" % (x[0], "ok" if x[1] else "NOK"), checks)
  for i in c:
    print(i)
  values = [
    ('check_sum', '%08x', kh.read_check_sum()),
    ('base_addr', '%08x', kh.get_base_addr()),
    ('boot_pc', '%08x', kh.read_boot_pc()),
    ('rom_rev', '%d.%d', kh.read_rom_ver_rev()),
    ('exec_rev', '%d.%d', kh.read_exec_ver_rev())
  ]
  v = map(lambda x:"%-20s  %s" % (x[0], x[1] % x[2]), values)
  for i in v:
    print(i)


def setup_list_parser(parser):
  parser.add_argument('-r', '--rom', default=None,
                      help='query rom name by wildcard')
  parser.add_argument('-e', '--entries', default=False, action='store_true',
                      help="show entries of ROMs")
  parser.set_defaults(cmd=do_list_cmd)


def setup_query_parser(parser):
  parser.add_argument('rom_image',
                      help='rom image to be checked')
  parser.add_argument('-m', '--module', default=None,
                      help='query module by wildcard')
  parser.set_defaults(cmd=do_query_cmd)


def setup_split_parser(parser):
  parser.add_argument('rom_image',
                      help='rom image file to be split')
  parser.add_argument('-o', '--output-dir',
                      help='store modules in this base dir')
  parser.add_argument('-m', '--module', default=None,
                      help='query module by wildcard')
  parser.add_argument('--no-version-dir', default=False, action='store_true',
                      help="do not create sub directory with version name")
  parser.add_argument('--no-index', default=False, action='store_true',
                      help="do not create an 'index.txt' in output path")
  parser.set_defaults(cmd=do_split_cmd)


def setup_build_parser(parser):
  parser.add_argument('modules', default=[], action='append',
                      help='modules or index.txt files to be added')
  parser.add_argument('-o', '--output',
                      help='rom image file to be built')
  parser.add_argument('-t', '--rom-type', default='kick',
                      help="what type of ROM to build (kick, ext)")
  parser.add_argument('-s', '--rom-size', default=512, type=int,
                      help="size of ROM in KiB")
  parser.add_argument('-a', '--kick-addr', default="f80000",
                      help="base address of Kick ROM in hex")
  parser.add_argument('-e', '--ext-addr', default="e00000",
                      help="base address of Ext ROM in hex")
  parser.add_argument('-f', '--add-footer', default=False, action='store_true',
                      help="add footer with check sum to Ext ROM")
  parser.add_argument('-r', '--rom-rev', default=None,
                      help="set ROM revision, e.g. 45.10")
  parser.add_argument('-k', '--kickety_split', default=False, action='store_true',
                      help="add 'kickety split' romhdr at center of 512k ROM")
  parser.add_argument('-b', '--fill-byte', default='ff',
                      help="fill byte in hex for empty ranges")
  parser.set_defaults(cmd=do_build_cmd)


def setup_diff_parser(parser):
  parser.add_argument('image_a', help='rom image a')
  parser.add_argument('image_b', help='rom image b')
  parser.add_argument('-s', '--same', default=False, action='store_true',
                      help="show same lines of ROMs")
  parser.add_argument('-a', '--show-address', default=False, action='store_true',
                      help="show KickROM address (otherwise image offset)")
  parser.add_argument('-b', '--rom-addr', default=None,
                      help="use hex base address for output")
  parser.add_argument('-f', '--force', default=False, action='store_true',
                      help="diff ROMs even if size differs")
  parser.add_argument('-c', '--columns', default=8, type=int,
                      help="number of bytes shown per line")
  parser.set_defaults(cmd=do_diff_cmd)


def setup_dump_parser(parser):
  parser.add_argument('image', help='rom image to be dumped')
  parser.add_argument('-a', '--show-address', default=False, action='store_true',
                      help="show KickROM address (otherwise image offset)")
  parser.add_argument('-b', '--rom-addr', default=None,
                      help="use hex base address for output")
  parser.add_argument('-c', '--columns', default=16, type=int,
                      help="number of bytes shown per line")
  parser.set_defaults(cmd=do_dump_cmd)


def setup_info_parser(parser):
  parser.add_argument('image', help='rom image to be analyzed')
  parser.set_defaults(cmd=do_info_cmd)


def parse_args():
  """parse args and return (args, opts)"""
  parser = argparse.ArgumentParser(description=desc)

  # global options
  parser.add_argument('-k', '--rom-key', default='rom.key',
                      help='the path of a rom.key file if you want to process'
                           ' crypted ROMs')
  add_logging_options(parser)

  # sub parsers
  sub_parsers = parser.add_subparsers(help="sub commands")
  # list
  list_parser = sub_parsers.add_parser('list', help='list ROMs in split data')
  setup_list_parser(list_parser)
  # query
  query_parser = sub_parsers.add_parser('query', help='query if ROM is in split data')
  setup_query_parser(query_parser)
  # split
  split_parser = sub_parsers.add_parser('split', help='split a ROM into modules')
  setup_split_parser(split_parser)
  # build
  build_parser = sub_parsers.add_parser('build', help='build a ROM from modules')
  setup_build_parser(build_parser)
  # diff
  diff_parser = sub_parsers.add_parser('diff', help='show differences in two ROM images')
  setup_diff_parser(diff_parser)
  # dump
  dump_parser = sub_parsers.add_parser('dump', help='dump a ROM image')
  setup_dump_parser(dump_parser)
  # info
  info_parser = sub_parsers.add_parser('info', help='print infos on a ROM image')
  setup_info_parser(info_parser)

  # parse
  return parser.parse_args()


# ----- main -----
def main():
  # parse args and init logging
  args = parse_args()
  setup_logging(args)
  # say hello
  logging.info("Welcom to romtool")
  # run command
  try:
    return args.cmd(args)
  except IOError as e:
    logging.error("IO Error: %s", e)
    return 1


# ----- entry point -----
if __name__ == '__main__':
  sys.exit(main())
