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

if [ ! -z "$1" ]; then
  build_clangd $1
else
  build_clangd debian-8
  build_clangd ubuntu-14.04
  build_clangd ubuntu-16.04
  build_clangd fedora
fi
