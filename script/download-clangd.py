#!/usr/bin/env python

import sys, os
repo_path = os.path.abspath(os.path.join(__file__, '..', '..'))
sys.path.insert(0, os.path.join(repo_path, 'python'))

from clangd.binary_downloader import BinaryDownloader
if __name__ == '__main__':
    script_path = os.path.abspath(os.path.join(repo_path, 'script'))
    downloader = BinaryDownloader()
    downloader.downloadBinary(script_path)
    print("download finished")
