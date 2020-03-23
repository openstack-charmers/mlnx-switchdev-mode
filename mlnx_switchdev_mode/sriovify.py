#!/usr/bin/env python
#
# Copyright 2019 Canonical Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import json
import logging
import os
import subprocess


class PCIDevice(object):
    """Helper class for interaction with a PCI device"""

    def __init__(self, pci_addr: str):
        """Initialise a new PCI device handler

        :param pci_addr: PCI address of device
        :type: str
        """
        self.pci_addr = pci_addr

    @property
    def path(self) -> str:
        """/sys path for PCI device

        :return: full path to PCI device in /sys filesystem
        :rtype: str
        """
        return "/sys/bus/pci/devices/{}".format(self.pci_addr)

    def subpath(self, subpath: str) -> str:
        """/sys subpath helper for PCI device

        :param subpath: subpath to construct path for
        :type: str
        :return: self.path + subpath
        :rtype: str
        """
        return os.path.join(self.path, subpath)

    @property
    def driver(self) -> str:
        """Kernel driver for PCI device

        :return: kernel driver in use for device
        :rtype: str
        """
        return os.path.basename(os.readlink(self.subpath("driver")))

    @property
    def bound(self) -> bool:
        """Determine if device is bound to a kernel driver

        :return: whether device is bound to a kernel driver
        :rtype: bool
        """
        return os.path.exists(self.subpath("driver"))

    @property
    def is_pf(self) -> bool:
        """Determine if device is a SR-IOV Physical Function

        :return: whether device is a PF
        :rtype: bool
        """
        return os.path.exists(self.subpath("sriov_numvfs"))

    @property
    def is_vf(self) -> bool:
        """Determine if device is a SR-IOV Virtual Function

        :return: whether device is a VF
        :rtype: bool
        """
        return os.path.exists(self.subpath("physfn"))

    @property
    def vf_addrs(self) -> list:
        """List Virtual Function addresses associated with a Physical Function

        :return: List of PCI addresses of Virtual Functions
        :rtype: list[str]
        """
        vf_addrs = []
        i = 0
        while True:
            try:
                vf_addrs.append(
                    os.path.basename(
                        os.readlink(self.subpath("virtfn{}".format(i)))
                    )
                )
            except FileNotFoundError:
                break
            i += 1
        return vf_addrs

    @property
    def vfs(self) -> list:
        """List Virtual Function associated with a Physical Function

        :return: List of PCI devices of Virtual Functions
        :rtype: list[PCIDevice]
        """
        return [PCIDevice(addr) for addr in self.vf_addrs]

    def devlink_get(self, obj_name: str):
        """Query devlink for information about the PCI device

        :param obj_name: devlink object to query
        :type: str
        :return: Dictionary of information about the device
        :rtype: dict
        """
        out = subprocess.check_output(
            [
                "/sbin/devlink",
                "dev",
                obj_name,
                "show",
                "pci/{}".format(self.pci_addr),
                "--json",
            ]
        )
        return json.loads(out)["dev"]["pci/{}".format(self.pci_addr)]

    def devlink_set(self, obj_name: str, prop: str, value: str):
        """Set devlink options for the PCI device

        :param obj_name: devlink object to set options on
        :type: str
        :param prop: property to set
        :type: str
        :param value: value to set for property
        :type: str
        """
        subprocess.check_call(
            [
                "/sbin/devlink",
                "dev",
                obj_name,
                "set",
                "pci/{}".format(self.pci_addr),
                prop,
                value,
            ]
        )

    def __str__(self) -> str:
        """String represenation of object

        :return: PCI address of string
        :rtype: str
        """
        return self.pci_addr


def netdev_sys(netdev: str, path: str) -> str:
    """Build path to netdev file system for a device

    :param netdev: netdev device address
    :type: str
    :param path: subpath to use
    :type: str
    :return: full path to netdev device
    :rtype: str
    """
    return os.path.join("/sys/class/net", netdev, path)


def build_pci_to_netdev() -> dict:
    """Query PCI device to netdev mappings

    :return: PCI device to netdev mappings
    :rtype: dict[str]
    """
    pci_to_netdev = {}
    for netdev in os.listdir("/sys/class/net"):
        try:
            pcidev = os.path.basename(
                os.readlink(netdev_sys(netdev, "device"))
            )
        except (FileNotFoundError, NotADirectoryError):
            continue
        pci_to_netdev[pcidev] = netdev
    return pci_to_netdev


def netdev_is_pf(netdev: str) -> bool:
    """Determine if netdev device is a SR-IOV Physical Function

    :param netdev: netdev device name
    :type: str
    :return: whether device is a PF
    :rtype: bool
    """
    try:
        return os.path.exists(netdev_sys(netdev, "device/sriov_numvfs"))
    except (FileNotFoundError, NotADirectoryError):
        return False


def netdev_is_vf(netdev: str) -> bool:
    """Determine if netdev device is a SR-IOV Virtual Function

    :param netdev: netdev device name
    :type: str
    :return: whether device is a VF
    :rtype: bool
    """
    try:
        return os.path.exists(netdev_sys(netdev, "device/physfn"))
    except (FileNotFoundError, NotADirectoryError):
        return False


def netdev_get_pf_pci(netdev: str) -> str:
    """Determine SR-IOV PF netdev for a SR-IOV VF netdev

    :param netdev: netdev device name
    :type: str
    :return: netdev device for VF's PF
    :rtype: str
    :raises: AssertionError if netdev is not a SR-IOV VF
    """
    assert netdev_is_vf(netdev)
    return os.path.basename(os.readlink(netdev_sys(netdev, "device/physfn")))


def netdev_get_driver(netdev: str) -> str:
    """Determine kernel driver for a netdev device

    :param netdev: netdev device name
    :type: str
    :return: Linux kernel driver in use
    :rtype: str
    """
    return os.path.basename(os.readlink(netdev_sys(netdev, "device/driver")))


def show():
    """Show details of all installed network adapters"""
    pci_to_netdev = build_pci_to_netdev()
    for pci, netdev in sorted(pci_to_netdev.items()):
        suffix = ""
        if netdev_is_pf(netdev):
            suffix = "PF"
        elif netdev_is_vf(netdev):
            phys_netdev = pci_to_netdev[netdev_get_pf_pci(netdev)]
            suffix = "VF of {}".format(phys_netdev)
        print(
            "{}\t{}\t{}\t{}".format(
                pci, netdev, netdev_get_driver(netdev), suffix
            )
        )


def switch():
    """Configure capable devices into switchdev mode"""
    for pci_addr in os.listdir("/sys/bus/pci/devices"):
        pcidev = PCIDevice(pci_addr)
        if pcidev.is_pf and pcidev.driver == "mlx5_core":
            print("{}: {}".format(pcidev, pcidev.vfs))
            if pcidev.vfs:
                if pcidev.devlink_get("eswitch")["mode"] == "legacy":
                    rebond = []
                    try:
                        for vf in pcidev.vfs:
                            if vf.bound:
                                with open(
                                    "/sys/bus/pci/drivers/mlx5_core/unbind",
                                    "wt",
                                ) as f:
                                    f.write(vf.pci_addr)
                                rebond.append(vf)
                        pcidev.devlink_set("eswitch", "mode", "switchdev")
                    finally:
                        for vf in rebond:
                            with open(
                                "/sys/bus/pci/drivers/mlx5_core/bind", "wt"
                            ) as f:
                                f.write(vf.pci_addr)


def main():
    parser = argparse.ArgumentParser("mlnx-switchdev-mode")
    parser.set_defaults(prog=parser.prog)
    subparsers = parser.add_subparsers(
        title="subcommands",
        description="valid subcommands",
        help="sub-command help",
    )
    show_subparser = subparsers.add_parser(
        "show", help="Show details of installed network adapters"
    )
    show_subparser.set_defaults(func=show)

    switch_subparser = subparsers.add_parser(
        "switch",
        help="Switch switchdev capable network adapters to switchdev mode",
    )
    switch_subparser.set_defaults(func=switch)

    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG)

    try:
        args.func()
    except Exception as e:
        raise SystemExit("{prog}: {msg}".format(prog=args.prog, msg=e))
