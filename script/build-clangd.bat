mkdir build-llvm
cd build-llvm
cmake -DCMAKE_BUILD_TYPE=Release \
     ../llvm-src
ninja clangd tools/clang/lib/Headers/clang-headers
cd ..

