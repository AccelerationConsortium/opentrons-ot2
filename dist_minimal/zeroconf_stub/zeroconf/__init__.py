"""Stub zeroconf package for systems without ARM wheels.

This provides the minimal interface that unitelabs-sila imports,
but doesn't actually do mDNS service discovery. When connecting
by direct IP/hostname, zeroconf is not needed.
"""

__version__ = "0.147.0"


class ServiceInfo:
    def __init__(self, *args, **kwargs):
        pass


class Zeroconf:
    def __init__(self, *args, **kwargs):
        pass

    def register_service(self, *args, **kwargs):
        pass

    def unregister_service(self, *args, **kwargs):
        pass

    def close(self):
        pass


class ServiceBrowser:
    def __init__(self, *args, **kwargs):
        pass

    def cancel(self):
        pass


class IPVersion:
    All = 0
    V4Only = 1
    V6Only = 2
