""" binary downloader """
import hashlib
from clangd import glog as log
import json
import platform
import os
import tarfile
from shutil import rmtree
from sys import platform as sys_platform
try:
    from urllib.request import urlretrieve
except ImportError:
    from urllib import urlretrieve
try:
    from urllib.request import urlopen
except ImportError:
    from urllib2 import urlopen

from clangd import vimsupport

DOWNLOAD_INDEX_URL = 'https://storage.googleapis.com/vim-clangd/REV308822/clangd-download-index.json'
DOWNLOAD_URL_PREFIX = 'https://storage.googleapis.com/vim-clangd/'

class BinaryDownloader(object):
    def __init__(self):
        pass

    def _HashCheck(self, file_path, algorithm, checksum):
        if not algorithm in ['md5', 'sha1']:
            return vimsupport.PresentYesOrNoDialog(
                'failed to do %s checksum on %s, should we use this file?' %
                (algorithm, file_path))
        with open(file_path, 'rb') as f:
            # osx get wrong result if not put in the same time
            if sys_platform != 'win32':
                os.fsync(f.fileno())
            h = hashlib.new(algorithm)
            while True:
                data = f.read(4096)
                if not data:
                    break
                h.update(data)
            if checksum == h.hexdigest():
                return True
        return vimsupport.PresentYesOrNoDialog(
            'failed to do %s checksum on %s, should we use this file?' %
            (algorithm, file_path))

    def _LoadDownloadIndex(self):
        response = urlopen(DOWNLOAD_INDEX_URL)
        html = response.read()
        data = json.loads(html.decode('utf-8'))
        return data

    def downloadBinary(self, script_path):
        supported_platforms = self._LoadDownloadIndex()
        plat = None

        is_linux = False
        is_win32 = False
        is_osx   = False
        if platform.system() == 'Linux':
            is_linux = True
            linux_dist = platform.dist()
            # dist turple is like this
            # Ubuntu, 16.04, Xenial
            # or Debian, 8.8, ''
            # fix for debian
            if linux_dist[0] == 'Debian':
                linux_dist[1] = str(int(linux_dist[1]))

            platform_desc = '-'.join(linux_dist)
        elif platform.system() == 'Darwin':
            is_osx = True
            v, _, _ = platform.mac_ver()
            mac_ver = '.'.join(v.split('.')[:2])
            platform_desc  = 'Mac OS X %s' % mac_ver
        elif platform.system() == 'Windows':
            is_win32 = True
            win_ver, _, _, _ = platform.win32_ver()
            platform_desc = 'Windows %s' % win_ver
        else:
            platform_desc = platform.system()

        log.info('detected platform %s' % platform_desc)

        for supported_platform in supported_platforms:
            if supported_platform['system'] == platform.system():
                if is_linux:
                    if supported_platform['dist'][0] != linux_dist[0] or supported_platform['dist'][1] != linux_dist[1] or supported_platform['dist'][2] != linux_dist[2]:
                        continue
                elif is_osx:
                    if float(mac_ver) < float(supported_platform['mac_ver']):
                        continue
                elif is_win32:
                    if float(win_ver) < float(supported_platform['win_ver']):
                        continue
                plat = supported_platform
                break
        if not plat:
            vimsupport.EchoMessage('non supported platform %s' % platform_desc)
            return
        if not plat['url'].startswith(DOWNLOAD_URL_PREFIX):
            vimsupport.EchoMessage('broken clangd %s' % plat['url'])
            return

        log.warn('downloading clangd binary from url %s' % plat['url'])

        tarball_file, _ = urlretrieve(plat['url'])

        if not self._HashCheck(tarball_file, 'md5', plat['md5sum']):
            vimsupport.EchoMessage('bad checksum clangd binary for platform %s' % platform_desc)
            return
        log.warn('downloaded clangd binary for platform %s' % platform_desc)

        for dir_name in ['bin', 'lib']:
            dir_path = os.path.join(script_path, dir_name)
            if os.path.exists(dir_path):
                rmtree(dir_path)
        tar = tarfile.open(name=tarball_file, mode='r:gz')
        tar.extractall(path=script_path)
        try:
            os.unlink(tarball_file)
        except OSError:
            pass
        vimsupport.EchoMessage('clangd installed')
