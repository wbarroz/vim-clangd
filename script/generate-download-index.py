#!/usr/bin/env python
import json
import glob
import sys, os

repo_path = os.path.abspath(os.path.join(__file__, '..', '..'))
script_path = os.path.abspath(os.path.join(repo_path, 'script'))

BUCKET_URL="https://storage.googleapis.com/vim-clangd"
INDEX_FILE_NAME="clangd-download-index.json"

BINARIES_MAPS = {
    "Darwin-16.7.0": {
        "name": "macosx-10.12",
        "system": "Darwin",
        "mac_ver": "10.12",
    },
    "Darwin-17.4.0": {
        "name": "macosx-10.13",
        "system": "Darwin",
        "mac_ver": "10.13",
    },
    "debian-8": {
        "name": "debian-8",
        "system": "Linux",
        "dist": ["Debian", "8", ""],
    },
    "debian-9": {
        "name": "debian-9",
        "system": "Linux",
        "dist": ["Debian", "9", ""],
    },
    "fedora-25": {
        "name": "fedora-25",
        "system": "Linux",
        "dist": ["Fedora", "25", ""],
    },
    "fedora-26": {
        "name": "fedora-26",
        "system": "Linux",
        "dist": ["Fedora", "26", ""],
    },
    "fedora-27": {
        "name": "fedora-27",
        "system": "Linux",
        "dist": ["Fedora", "27", ""],
    },
    "ubuntu-14.04": {
        "name": "ubuntu-14.04",
        "system": "Linux",
        "dist": ["Ubuntu", "14.04", "trusty"],
    },
    "ubuntu-16.04": {
        "name": "ubuntu-16.04",
        "system": "Linux",
        "dist": ["Ubuntu", "16.04", "xenial"],
    },
    "ubuntu-18.04": {
        "name": "ubuntu-18.04",
        "system": "Linux",
        "dist": ["Ubuntu", "18.04", "bionic"],
    },
    "vs2015-amd64": {
        "name": "vs2015-amd64",
        "system": "Windows",
        "win_ver": "7",
    }
}

def HashFile(file_path, algorithm = 'md5'):
    import hashlib
    if not algorithm in ['md5', 'sha1']:
        return None
    with open(file_path, 'rb') as f:
        h = hashlib.new(algorithm)
        while True:
            data = f.read(4096)
            if not data:
                break
            h.update(data)
        return h.hexdigest()
    return None

def generate_index(directory):
    results = []
    for binary in os.listdir(directory):
        if len(binary) < len("clangd-*.tar.gz"):
            continue
        tag = binary[len("clangd-"):-len(".tar.gz")]
        if tag in BINARIES_MAPS:
            print("Adding %s" % binary)
            result = BINARIES_MAPS[tag]
            result["url"] = BUCKET_URL + "/" + directory + "/" + binary
            result["md5sum"] = HashFile(os.path.join(directory, binary))
            results.append(result)

    return results

def get_llvm_commit():
    with open("clangd_commits") as f:
        while True:
            line = f.readline()
            if not line:
                break
            if line.startswith("LLVM_COMMIT="):
                LLVM_COMMIT = line[len("LLVM_COMMIT="):].strip()
    return LLVM_COMMIT

if __name__ == '__main__':
    os.chdir(script_path)
    LLVM_COMMIT = get_llvm_commit()
    results = generate_index(LLVM_COMMIT)
    index_file = os.path.join(LLVM_COMMIT, INDEX_FILE_NAME)
    with open(index_file, 'w') as f:
        f.write(json.dumps(results, sort_keys=True, indent=4, separators=(',', ': ')))
    print("%s written under directory %s" % (INDEX_FILE_NAME, LLVM_COMMIT))
