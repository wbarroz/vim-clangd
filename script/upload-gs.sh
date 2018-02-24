#!/usr/bin/env bash
set -e
cd "$(dirname "${BASH_SOURCE[0]}")"

# Google Cloud Bucket Structure
#
# -- gs://vim-clangd
#      |
#      |
#      |---- <LLVM_COMMIT1>
#      |         |----clangd-download-index.json
#      |         |----clangd-Darwin-17.4.0.tar.gz
#      |         |----clangd-Darwin-16.7.0.tar.gz
#      |         |----clangd-Darwin-debian-8.tar.gz
#      |         ...
#      |
#      |
#      |---- <LLVM_COMMIT2>
#      |         |----clangd-download-index.json
#      |         |----clangd-Darwin-17.4.0.tar.gz
#      |         |----clangd-Darwin-16.7.0.tar.gz
#      |         |----clangd-Darwin-debian-8.tar.gz
#      |         ...
#      |
#      |
#      ...

source clangd_commits

TARGET_BUCKET="gs://vim-clangd"
TARGET_SUBDIR=$LLVM_COMMIT
#gsutil ls gs://vim-clangd

if [ -z "$(which gsutil)" ]; then
  echo "Google Cloud SDK is not found on the path"
  echo "Please double check the setup or download a new installation from https://cloud.google.com/sdk/docs/"
  exit -1
fi

mkdir -p $TARGET_SUBDIR
echo "Copying binaries"
cp -f clangd-*.tar.gz $TARGET_SUBDIR
echo "Generating download index"
./generate-download-index.py
echo "Uploading files"
gsutil cp -r $TARGET_SUBDIR $TARGET_BUCKET
echo "Setting public permissions to files"
gsutil acl ch -r -u AllUsers:R $TARGET_BUCKET/$TARGET_SUBDIR
echo "$LLVM_COMMIT published"
