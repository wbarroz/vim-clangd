#!/usr/bin/env bash
set -e
cd "$(dirname "${BASH_SOURCE[0]}")"

build_clangd() {
  DISTRO=$1
  if [ ! -f Dockerfile.$DISTRO ]; then
    echo "unsupported distribution $DISTRO"
    return
  fi
  echo "Building clangd for $DISTRO"
  docker build -t clangd:$DISTRO -f Dockerfile.$DISTRO .
  docker run -it -v $PWD/../script:/build -w /build clangd:$DISTRO rm -rf lib bin build-llvm
  docker run -it -v $PWD/../script:/build -w /build clangd:$DISTRO ./build-clangd.sh
  tar -C ../script -czf clangd-$DISTRO.tar.gz bin lib
  echo "clangd tarball for $DISTRO is created"
}

if [ $# -ge 1  ]; then
  while (( "$#" )); do
    build_clangd $1
    shift
  done
else
  echo "No platforms specified, try to build all supported platforms"
  build_clangd debian-8
  build_clangd debian-9
  build_clangd ubuntu-14.04
  build_clangd ubuntu-16.04
  build_clangd ubuntu-18.04
  build_clangd fedora-25
  build_clangd fedora-26
  build_clangd fedora-27
fi
