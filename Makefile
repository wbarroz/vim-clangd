default: download-clangd

.PHONY: download-clangd build-clangd
download-clangd:
	script/download-clangd.py

build-clangd:
	script/build-clangd.sh
