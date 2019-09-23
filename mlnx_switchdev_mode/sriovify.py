#!/usr/bin/env python

import json
import os
import subprocess


class PCIDevice(object):

    def __init__(self, pci_addr):
        self.pci_addr = pci_addr

    @property
    def path(self):
        return '/sys/bus/pci/devices/{}'.format(self.pci_addr)

    def subpath(self, subpath):
        return '{}/{}'.format(self.path, subpath)

    @property
    def driver(self):
        return os.path.basename(os.readlink(self.subpath('driver')))

    @property
    def is_pf(self):
        return os.path.exists(self.subpath('sriov_numvfs'))

    @property
    def is_vf(self):
        return os.path.exists(self.subpath('physfn'))

    @property
    def vf_addrs(self):
        vf_addrs = []
        i = 0
        while True:
            try:
                vf_addrs.append(
                    os.path.basename(
                        os.readlink(
                            self.subpath('virtfn{}'.format(i))
                        )
                    )
                )
            except FileNotFoundError:
                break
            i += 1
        return vf_addrs

    @property
    def vfs(self):
        return [PCIDevice(addr) for addr in self.vf_addrs]

    def devlink_get(self, obj_name):
        out = subprocess.check_output(
            ['/sbin/devlink', 'dev', obj_name,
             'show', 'pci/{}'.format(self.pci_addr),
             '--json']
        )
        return json.loads(out)['dev']['pci/{}'.format(self.pci_addr)]

    def devlink_set(self, obj_name, prop, value):
        subprocess.check_call(
            ['/sbin/devlink', 'dev', obj_name,
             'set', 'pci/{}'.format(self.pci_addr),
             prop, value]
        )


def netdev_sys(netdev, path):
    return os.path.join('/sys/class/net', netdev, path)


def build_pci_to_netdev():
    pci_to_netdev = {}
    for netdev in os.listdir('/sys/class/net'):
        try:
            pcidev = os.path.basename(
                os.readlink(netdev_sys(netdev, 'device'))
            )
        except (FileNotFoundError, NotADirectoryError):
            continue
        pci_to_netdev[pcidev] = netdev
    return pci_to_netdev


def netdev_is_pf(netdev):
    try:
        return os.path.exists(netdev_sys(netdev, 'device/sriov_numvfs'))
    except (FileNotFoundError, NotADirectoryError):
        return False


def netdev_is_vf(netdev):
    try:
        return os.path.exists(netdev_sys(netdev, 'device/physfn'))
    except (FileNotFoundError, NotADirectoryError):
        return False


def netdev_get_pf_pci(netdev):
    assert netdev_is_vf(netdev)
    return os.path.basename(os.readlink(netdev_sys(netdev, 'device/physfn')))


def netdev_get_driver(netdev):
    return os.path.basename(os.readlink(netdev_sys(netdev, 'device/driver')))


def main():
    pci_to_netdev = build_pci_to_netdev()

    for pci, netdev in sorted(pci_to_netdev.items()):
        suffix = ''
        if netdev_is_pf(netdev):
            suffix = 'PF'
        elif netdev_is_vf(netdev):
            phys_netdev = pci_to_netdev[netdev_get_pf_pci(netdev)]
            suffix = 'VF of %s' % phys_netdev
        print('%s\t%s\t%s\t%s' % (pci, netdev,
                                  netdev_get_driver(netdev), suffix))

    for pci_addr in os.listdir('/sys/bus/pci/devices'):
        pcidev = PCIDevice(pci_addr)
        if pcidev.is_pf and pcidev.driver == 'mlx5_core':
            print('{}: {}'.format(pcidev.pci_addr, pcidev.vfs))
            if pcidev.vf_addrs:
                if pcidev.devlink_get('eswitch')['mode'] == 'legacy':
                    for vf_addr in pcidev.vf_addrs:
                        with open('/sys/bus/pci/drivers/mlx5_core/unbind',
                                  'wt') as f:
                            f.write(vf_addr)
                    pcidev.devlink_set('eswitch', 'mode', 'switchdev')
                    for vf_addr in pcidev.vf_addrs:
                        with open('/sys/bus/pci/drivers/mlx5_core/bind',
                                  'wt') as f:
                            f.write(vf_addr)
