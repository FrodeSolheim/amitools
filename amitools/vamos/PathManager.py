import os.path
import os
from Log import log_path
from Exceptions import *
from VolumeManager import VolumeManager
from AssignManager import AssignManager

class PathManager:
  
  def __init__(self):
    self.vol_mgr = VolumeManager()
    self.assign_mgr = AssignManager(self.vol_mgr)
    self.paths = []
  
  def parse(self, cfg, volume_strs=None, assign_strs=None, auto_assign=None, path_strs=None):
    # volumes
    self.vol_mgr.parse_config(cfg)
    self.vol_mgr.parse_strings(volume_strs)
    self.vol_mgr.config_done()
    # assign
    self.assign_mgr.parse_config(cfg)
    self.assign_mgr.parse_strings(assign_strs)
    self.assign_mgr.set_auto_assign(auto_assign)
    # done
    self._parse_config(cfg)
    self._parse_strings(path_strs)
    self._config_done()
  
  def _parse_config(self, cfg):
    if cfg == None:
      return
    sect = 'path'
    if cfg.has_option(sect, 'path'):
      p = cfg.get(sect, 'path')
      if p != None:
        self.add_path(p)
    
  def _parse_strings(self, path_strs):
    if path_strs == None:
      return
    for p in path_strs:
      self.add_path(p)
  
  def add_path(self, paths):
    # append assign or clear first?
    if len(paths)>0 and paths[0] == '+':
      paths = paths[1:]
    else:
      self.paths = []
    # split multi assign
    path_list = paths.split(',')
    if path_list == None:
      raise VamosConfigError("invalid path: %s" % name)
    # add assign
    if len(path_list) > 0:
      for p in path_list:
        # ensure slash at end if not a colon
        if p[-1] != ':' and p[-1] != '/' and p != '.':
          p += '/'
        self.paths.append(p)
  
  def _config_done(self):    
    # set current device and path name
    cur_sys = os.getcwd()
    cur_ami = self.vol_mgr.sys_to_ami_path_pair(cur_sys)
    if cur_ami == None:
      raise VamosConfigError("Can't map current directory to amiga path: '%s'" % cur_sys)
    self.cur_vol  = cur_ami[0]
    self.cur_path = cur_ami[1]
    self.org_cur_vol = cur_ami[0]
    self.org_cur_path = cur_ami[1]
    log_path.info("current amiga dir: '%s:%s'" % (self.cur_vol, self.cur_path))
    # ensure path
    if len(self.paths)==0:
      self.paths = ['.','c:']
    log_path.info("path: %s" % map(str, self.paths))
  
  # current path handling
  
  def set_cur_path(self, full_path):
    split = self.assign_mgr.ami_path_split_volume(full_path)
    if split == None:
      raise ValueError("set_cur_path needs a path with device name!")
    self.cur_vol = split[0]
    self.cur_path = split[1]
    log_path.info("set current: dev='%s' path='%s'" % (self.cur_vol, self.cur_path))
  
  def get_cur_path(self):
    return (self.cur_vol, self.cur_path)
  
  def set_default_cur_path(self):
    self.cur_vol  = self.org_cur_vol
    self.cur_path = self.org_cur_path
    log_path.info("reset current: dev='%s' path='%s'" % (self.cur_vol, self.cur_path))

  def ami_abs_cur_path(self):
    return self.cur_vol + ":" + self.cur_path

  # ----- API -----

  def get_all_volume_names(self):
    return self.vol_mgr.get_all_names()

  def ami_command_to_sys_path(self, ami_path):
    """lookup a command on path if it does not contain a relative or absolute path
       otherwise perform normal 'ami_to_sys_path' conversion"""
    sys_path = None
    # is not a command only
    if ami_path.find(':') != -1 or ami_path.find('/') != -1:
      check_path = self.ami_to_sys_path(ami_path)
      # make sure its a file
      if check_path != None and os.path.isfile(check_path):
        sys_path = check_path
    else:
      # try all path
      for path in self.paths:
        # special case: current dir
        if path == '.':
          try_ami_path = ami_path
        else:
          try_ami_path = path + ami_path
        check_path = self.ami_to_sys_path(try_ami_path, mustExist=True)
        log_path.info("ami_command_to_sys_path: try_ami_path='%s' -> sys_path='%s'" % (try_ami_path, check_path))
        # make sure its a file
        if check_path != None and os.path.isfile(check_path):
          sys_path = check_path
          break
        
    if sys_path != None:
      log_path.info("ami_command_to_sys_path: ami_path=%s -> sys_path=%s" % (ami_path, sys_path))
      return sys_path
    else:
      log_path.warn("ami_command_to_sys_path: ami_path='%s' not found!" % (ami_path))
      return None

  def ami_to_sys_path(self, ami_path, searchMulti=False, mustExist=False):
    # first get an absolute amiga path
    abs_path = self.ami_abs_path(ami_path)
    # replace assigns
    norm_paths = self.assign_mgr.ami_path_resolve(abs_path)
    if len(norm_paths) == 0:
      log_path.warn("ami_to_sys_path: ami_path='%s' -> abs_path='%s' -> no resolved paths!" % (ami_path, abs_path))
      return None
    # now we have paths with volume:abs/path
    sys_path = None
    # search for existing multi assign
    if searchMulti or mustExist:
      for npath in norm_paths:
        # first try to find existing path in all locations
        spath = self.vol_mgr.ami_to_sys_path(npath, mustExist=True)
        if spath != None:
          sys_path = spath
          break
    # nothing found -> try first path
    if sys_path == None and not mustExist:
      sys_path = self.vol_mgr.ami_to_sys_path(norm_paths[0], mustExist=False)
    log_path.info("ami_to_sys_path: ami_path='%s' -> abs_path='%s' -> norm_path='%s' -> sys_path='%s'" % (ami_path, abs_path, norm_paths, sys_path))
    return sys_path

  def sys_to_ami_path(self, sys_path):
    abs_path = os.path.abspath(sys_path)
    ami_path = self.vol_mgr.sys_to_ami_path(abs_path)
    log_path.info("sys_to_ami_path: sys_path='%s' -> abs_path='%s' -> ami_path='%s'" % (sys_path, abs_path, ami_path))
    return ami_path
  
  def ami_abs_parent_path(self, path):
    """return absolute parent path of given path or same if already parent"""
    # can't strip from device prefix
    if path[-1] == ':':
      return path
    # skip trailing slash
    if path[-1] == '/':
      return self.ami_strip_name(self, path[:-2])
    # make absolute first
    if path.find(':') < 1:
      path = self.ami_abs_path(path)
    pos = path.rfind('/')
    # skip last part
    if pos != -1:
      return path[0:pos]
    # keep only device
    else:
      pos = path.find(':')
      return path[0:pos+1]
  
  def ami_abs_path(self, path):
    """return absolute amiga path from given path"""
    # current dir
    if path == "":
      return self.cur_vol + ":" + self.cur_path
    col_pos = path.find(':')
    # already with device name
    if col_pos > 0:
      return path
    # relative to cur device
    elif col_pos == 0:
      abs_prefix = self.cur_vol + ":"
      path = path[1:]
      # invalid parent path of root? -> remove
      if len(path)>0 and path[0] == '/':
        path = path[1:]
    # no path given -> return current path
    elif path == '':
      return self.cur_vol + ":" + self.cur_path      
    # a parent path is given
    elif path[0] == '/':
      abs_prefix = self.ami_abs_parent_path(self.cur_vol + ":" + self.cur_path)
    # cur path
    else:
      abs_prefix = self.cur_vol + ":" + self.cur_path
      if self.cur_path != '':
        abs_prefix += '/'
    return abs_prefix + path

  def ami_name_of_path(self, path):
    l = len(path)
    # no path given
    if l == 0:
      return path
    # ends with colon
    if path[-1] == ':':
      if l == 1:
        return self.cur_vol
      else:
        return path[:-1]
    # has slash?
    pos = path.rfind('/')
    if pos != -1:
      return path[pos+1:]
    # has colon?
    pos = path.rfind(':')
    if pos != -1:
      return path[pos+1:]
    # is relative
    return path

  def ami_volume_of_abspath(self, path):
    pos = path.find(':')
    return path[:pos]
    
  def ami_volume_of_path(self, path):
    return self.ami_volume_of_abspath(self.ami_abs_path(path))

  def ami_list_dir(self, ami_path):
    sys_path = self.ami_to_sys_path(ami_path, mustExist=True)
    if sys_path == None:
      return None
    if not os.path.isdir(sys_path):
      return None
    files = os.listdir(sys_path)
    return files
    
  def ami_path_exists(self, ami_path):
    sys_path = self.ami_to_sys_path(ami_path, mustExist=True)
    return sys_path != None

  def ami_path_join(self, a, b):
    if len(a) == 0:
      return b
    elif len(b) == 0:
      return a
    else:
      return a + b
      
    
    