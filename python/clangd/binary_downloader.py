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

try:
    from clangd.vimsupport import PresentYesOrNoDialog,EchoMessage
except ImportError:
    def PresentYesOrNoDialog(s):
        pass

    def EchoMessage(s):
        log.info(s)

LLVM_COMMIT = "796005d4a195f37222d7f63dc38b7b8ffe8cef6d"
DOWNLOAD_INDEX_URL_FORMAT = 'https://storage.googleapis.com/vim-clangd/%s/clangd-download-index.json'
DOWNLOAD_URL_PREFIX = 'https://storage.googleapis.com/vim-clangd/'


def HashFile(file_path, algorithm):
    if not algorithm in ['md5', 'sha1']:
        return None
    with open(file_path, 'rb') as f:
        # FIXME is it necessary?
        # osx get wrong result if not put in the same time
        if sys_platform != 'msys' and sys_platform != 'win32':
            os.fsync(f.fileno())
        h = hashlib.new(algorithm)
        while True:
            data = f.read(4096)
            if not data:
                break
            h.update(data)
        return h.hexdigest()
    return None

class BinaryDownloader(object):
    def __init__(self):
        pass

    def _LoadDownloadInfo(self):
        url = DOWNLOAD_INDEX_URL_FORMAT % LLVM_COMMIT
        response = urlopen(url)
        html = response.read()
        data = json.loads(html.decode('utf-8'))
        return data

    def _DetectBinaryUrl(self):
        platform_system = platform.system()
        if platform_system == 'Linux':
            linux_dist = platform.dist()
            # dist turple is like this
            # Ubuntu, 16.04, Xenial
            # or Debian, 8.8, ''
            # fix for debian
            if linux_dist[0].lower() == 'debian':
                linux_dist[1] = str(int(linux_dist[1]))
            platform_version = float(linux_dist[1])
            platform_desc = '%s %s' % (linux_dist[0], platform_version)
        elif platform_system == 'Darwin':
            v, _, _ = platform.mac_ver()
            mac_ver = '.'.join(v.split('.')[:2])
            platform_version = float(mac_ver)
            platform_desc = 'Mac OS X %s' % mac_ver
        elif platform_system == 'Windows':
            win_ver, _, _, _ = platform.win32_ver()
            platform_version = float(win_ver)
        elif platform_system.startswith('MINGW64_NT'):
            # use msvc binary temporarily
            win_ver = float(platform_system.split('-')[1])
            platform_system = 'Windows'
            platform_version = float(win_ver)
        else:
            platform_system = 'Unknown System'
            platform_version = 0.0

        if not platform_desc:
            platform_desc = '%s %f' % (platform_system, platform_version)

        log.warn('detected %s' % platform_desc)

        download_infos = self._LoadDownloadInfo()
        # try to match from a set of download infos
        plats = []
        for plat in download_infos:
            # not trust url outside our mirror site
            if not plat['url'].startswith(DOWNLOAD_URL_PREFIX):
                continue
            if plat['system'] == platform_system:
                if platform_system == 'Linux':
                    if plat['dist'][0].lower() != linux_dist[0].lower():
                        continue
                    plat['version'] = float(plat['dist'][1])
                elif platform_system == 'Darwin':
                    plat['version'] = float(plat['mac_ver'])
                elif platform_system == 'Windows':
                    plat['version'] = float(plat['win_ver'])
                if platform_version < plat['version']:
                    continue
                plats.append(plat)
        if not plats:
            return platform_desc, None
        plats.sort(key=lambda x : x['version'], reverse=True)
        return platform_desc, plats[0]

    def downloadBinary(self, script_path):
        platform_desc, plat = self._DetectBinaryUrl()
        if not plat:
            EchoMessage('non supported platform %s' % platform_desc)
            return

        log.warn('downloading clangd binary from url %s' % plat['url'])

        tarball_file, _ = urlretrieve(plat['url'])

        if not plat['md5sum'] or not HashFile(tarball_file, 'md5') == plat['md5sum']:
            if not PresentYesOrNoDialog(
                    'failed to do checksum on %s, should we use this file?' %
                    tarball_file):
                return
        log.warn('downloaded clangd binary to %s' % tarball_file)

        for dir_name in ['bin', 'lib']:
            dir_path = os.path.join(script_path, dir_name)
            if os.path.exists(dir_path):
                rmtree(dir_path)
        tar = tarfile.open(name=tarball_file, mode='r:gz')
        tar.extractall(path=script_path)
        try:
            os.unlink(tarball_file)
            log.info('removed temporary file %s' % tarball_file)
        except OSError:
            log.warn('failed to remove temporary file %s' % tarball_file)
            pass
        EchoMessage('clangd installed')
