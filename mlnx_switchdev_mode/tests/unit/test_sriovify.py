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

import mock
import os
import unittest

from mlnx_switchdev_mode import sriovify


NETDEV_DEVICES = {
    "/sys/class/net/eno1": {
        "device": "../../../0000:01:00.0",
        "device/driver": "../../../../bus/pci/drivers/ixgbe",
    },
    "/sys/class/net/eno2": {
        "device": "../../../0000:01:00.1",
        "device/driver": "../../../../bus/pci/drivers/ixgbe",
    },
    "/sys/class/net/eno3": {
        "device": "../../../0000:05:00.0",
        "device/driver": "../../../../bus/pci/drivers/igb",
    },
    "/sys/class/net/eno4": {
        "device": "../../../0000:05:00.1",
        "device/driver": "../../../../bus/pci/drivers/igb",
    },
    "/sys/class/net/enp130s0f0": {
        "device": "../../../0000:82:00.0",
        "device/sriov_numvfs": 127,
        "device/driver": "../../../../bus/pci/drivers/ixgbe",
    },
    "/sys/class/net/enp130s0f1": {
        "device": "../../../0000:82:00.1",
        "device/sriov_numvfs": 127,
        "device/driver": "../../../../bus/pci/drivers/ixgbe",
    },
    "/sys/class/net/enp3s0f0": {
        "device": "../../../0000:03:00.0",
        "device/sriov_numvfs": 127,
        "device/driver": "../../../../bus/pci/drivers/mlx5_core",
    },
    "/sys/class/net/enp3s0f1": {
        "device": "../../../0000:03:00.1",
        "device/sriov_numvfs": 127,
        "device/driver": "../../../../bus/pci/drivers/mlx5_core",
    },
    "/sys/class/net/enp3s0f2": {
        "device": "../../../0000:03:00.2",
        "device/driver": "../../../../bus/pci/drivers/mlx5_core",
        "device/physfn": "../0000:03:00.0",
    },
    "/sys/class/net/enp3s0f3": {
        "device": "../../../0000:03:00.3",
        "device/driver": "../../../../bus/pci/drivers/mlx5_core",
        "device/physfn": "../0000:03:00.1",
    },
}


def netdev_readlink_helper(path):
    for device, subpaths in NETDEV_DEVICES.items():
        if path.startswith(device):
            for subpath, target in subpaths.items():
                full_path = os.path.join(device, subpath)
                if path == full_path:
                    return target
    return None


def netdev_exists_helper(path):
    for device, subpaths in NETDEV_DEVICES.items():
        if path.startswith(device):
            subpath = path.lstrip(device).rstrip("/")
            return subpath in subpaths
    return False


class TestNetdevHelpers(unittest.TestCase):
    @mock.patch("os.path.exists", side_effect=netdev_exists_helper)
    @mock.patch("os.readlink", side_effect=netdev_readlink_helper)
    def test_netdev_is_pf(self, _readlink, _exists):
        self.assertTrue(sriovify.netdev_is_pf("enp3s0f0"))
        self.assertFalse(sriovify.netdev_is_pf("eno2"))

    @mock.patch("os.path.exists", side_effect=netdev_exists_helper)
    @mock.patch("os.readlink", side_effect=netdev_readlink_helper)
    def test_netdev_is_vf(self, _readlink, _exists):
        self.assertTrue(sriovify.netdev_is_vf("enp3s0f2"))
        self.assertFalse(sriovify.netdev_is_vf("enp3s0f0"))

    @mock.patch("os.path.exists", side_effect=netdev_exists_helper)
    @mock.patch("os.readlink", side_effect=netdev_readlink_helper)
    def test_netdev_get_pf_pci(self, _readlink, _exists):
        self.assertEqual(
            sriovify.netdev_get_pf_pci("enp3s0f2"), "0000:03:00.0"
        )
        self.assertEqual(
            sriovify.netdev_get_pf_pci("enp3s0f3"), "0000:03:00.1"
        )
        with self.assertRaises(AssertionError):
            sriovify.netdev_get_pf_pci("enp3s0f1")

    @mock.patch("os.path.exists", side_effect=netdev_exists_helper)
    @mock.patch("os.readlink", side_effect=netdev_readlink_helper)
    def test_netdev_get_driver(self, _readlink, _exists):
        self.assertEqual(sriovify.netdev_get_driver("enp3s0f0"), "mlx5_core")
        self.assertEqual(sriovify.netdev_get_driver("eno2"), "ixgbe")

    @mock.patch("os.listdir", return_value=NETDEV_DEVICES.keys())
    @mock.patch("os.path.exists", side_effect=netdev_exists_helper)
    @mock.patch("os.readlink", side_effect=netdev_readlink_helper)
    def test_build_pci_to_netdev(self, _readlink, _exists, _listdir):
        self.assertEqual(
            sriovify.build_pci_to_netdev(),
            {
                "0000:01:00.0": "/sys/class/net/eno1",
                "0000:01:00.1": "/sys/class/net/eno2",
                "0000:03:00.0": "/sys/class/net/enp3s0f0",
                "0000:03:00.1": "/sys/class/net/enp3s0f1",
                "0000:03:00.2": "/sys/class/net/enp3s0f2",
                "0000:03:00.3": "/sys/class/net/enp3s0f3",
                "0000:05:00.0": "/sys/class/net/eno3",
                "0000:05:00.1": "/sys/class/net/eno4",
                "0000:82:00.0": "/sys/class/net/enp130s0f0",
                "0000:82:00.1": "/sys/class/net/enp130s0f1",
            },
        )
