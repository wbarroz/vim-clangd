from sys import version_info
PY_VERSION = version_info[0]
PY2 = PY_VERSION  == 2

def PyVersion():
    return PY_VERSION

