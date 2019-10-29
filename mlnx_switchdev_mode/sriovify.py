#!/usr/bin/env python

import argparse
import json
import logging
import os
import subprocess


class PCIDevice(object):

    def __init__(self, pci_addr: str):
        self.pci_addr = pci_addr

    @property
    def path(self) -> str:
        return '/sys/bus/pci/devices/{}'.format(self.pci_addr)

    def subpath(self, subpath: str) -> str:
        return '{}/{}'.format(self.path, subpath)

    @property
    def driver(self) -> str:
        return os.path.basename(os.readlink(self.subpath('driver')))

    @property
    def bound(self) -> bool:
        return os.path.exists(self.subpath('driver'))

    @property
    def is_pf(self) -> bool:
        return os.path.exists(self.subpath('sriov_numvfs'))

    @property
    def is_vf(self) -> bool:
        return os.path.exists(self.subpath('physfn'))

    @property
    def vf_addrs(self) -> list:
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
    def vfs(self) -> list:
        return [PCIDevice(addr) for addr in self.vf_addrs]

    def devlink_get(self, obj_name: str):
        out = subprocess.check_output(
            ['/sbin/devlink', 'dev', obj_name,
             'show', 'pci/{}'.format(self.pci_addr),
             '--json']
        )
        return json.loads(out)['dev']['pci/{}'.format(self.pci_addr)]

    def devlink_set(self, obj_name: str, prop: str, value: str):
        subprocess.check_call(
            ['/sbin/devlink', 'dev', obj_name,
             'set', 'pci/{}'.format(self.pci_addr),
             prop, value]
        )

    def __str__(self) -> str:
        return self.pci_addr


def netdev_sys(netdev: str, path: str) -> str:
    return os.path.join('/sys/class/net', netdev, path)


def build_pci_to_netdev() -> dict:
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


def netdev_is_pf(netdev: str) -> bool:
    try:
        return os.path.exists(netdev_sys(netdev, 'device/sriov_numvfs'))
    except (FileNotFoundError, NotADirectoryError):
        return False


def netdev_is_vf(netdev: str) -> bool:
    try:
        return os.path.exists(netdev_sys(netdev, 'device/physfn'))
    except (FileNotFoundError, NotADirectoryError):
        return False


def netdev_get_pf_pci(netdev: str) -> str:
    assert netdev_is_vf(netdev)
    return os.path.basename(os.readlink(netdev_sys(netdev, 'device/physfn')))


def netdev_get_driver(netdev: str) -> str:
    return os.path.basename(os.readlink(netdev_sys(netdev, 'device/driver')))


def show():
    """Show details of all installed network adapters"""
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


def switch():
    """Configure capable devices into switchdev mode"""
    for pci_addr in os.listdir('/sys/bus/pci/devices'):
        pcidev = PCIDevice(pci_addr)
        if pcidev.is_pf and pcidev.driver == 'mlx5_core':
            print('{}: {}'.format(pcidev, pcidev.vfs))
            if pcidev.vfs:
                if pcidev.devlink_get('eswitch')['mode'] == 'legacy':
                    rebond = []
                    try:
                        for vf in pcidev.vfs:
                            if vf.bound:
                                with open('/sys/bus/pci/drivers/'
                                          'mlx5_core/unbind',
                                          'wt') as f:
                                    f.write(vf.pci_addr)
                                rebond.append(vf)
                        pcidev.devlink_set('eswitch', 'mode', 'switchdev')
                    finally:
                        for vf in rebond:
                            with open('/sys/bus/pci/drivers/mlx5_core/bind',
                                      'wt') as f:
                                f.write(vf.pci_addr)


def main():
    parser = argparse.ArgumentParser('mlnx-switchdev-mode')
    parser.set_defaults(prog=parser.prog)
    subparsers = parser.add_subparsers(
        title="subcommands",
        description="valid subcommands",
        help="sub-command help",
    )
    show_subparser = subparsers.add_parser(
        'show',
        help='Show details of installed network adapters'
    )
    show_subparser.set_defaults(func=show)

    switch_subparser = subparsers.add_parser(
        'switch',
        help='Switch switchdev capable network adapters to switchdev mode'
    )
    switch_subparser.set_defaults(func=switch)

    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG)

    try:
        args.func()
    except Exception as e:
        raise SystemExit(
            '{prog}: {msg}'.format(
                prog=args.prog,
                msg=e,
            )
        )
