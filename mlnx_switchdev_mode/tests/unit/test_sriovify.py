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

import functools
import io
import json
import os
import unittest
import unittest.mock as mock

from mlnx_switchdev_mode import sriovify


PCI_DEVICES = {
    "/sys/bus/pci/devices/0000:03:00.1": {
        "driver": "../../../../bus/pci/drivers/mlx5_core",
        "sriov_numvfs": 127,
        "virtfn0": "../0000:03:00.2",
        "virtfn1": "../0000:03:00.3",
    },
    "/sys/bus/pci/devices/0000:03:00.2": {"physfn": "../0000:03:00.1"},
    "/sys/bus/pci/devices/0000:03:00.3": {
        "driver": "../../../../bus/pci/drivers/mlx5_core",
        "physfn": "../0000:03:00.1",
    },
    "/sys/bus/pci/devices/0000:01:00.0": {
        "driver": "../../../../bus/pci/drivers/igb"
    },
}


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


def _readlink_helper(path, devices):
    for device, subpaths in devices.items():
        if path.startswith(device):
            for subpath, target in subpaths.items():
                full_path = os.path.join(device, subpath)
                if path == full_path:
                    return target
    raise FileNotFoundError(path)


def _exists_helper(path, devices):
    for device, subpaths in devices.items():
        if path.startswith(device):
            subpath = path.split(device)[-1].lstrip("/")
            return subpath in subpaths
    return False


netdev_exists_helper = functools.partial(
    _exists_helper, devices=NETDEV_DEVICES
)


netdev_readlink_helper = functools.partial(
    _readlink_helper, devices=NETDEV_DEVICES
)


pci_exists_helper = functools.partial(_exists_helper, devices=PCI_DEVICES)


pci_readlink_helper = functools.partial(_readlink_helper, devices=PCI_DEVICES)


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


class TestPCIDevice(unittest.TestCase):
    _device = sriovify.PCIDevice("0000:03:00.1")
    _unbound_device = sriovify.PCIDevice("0000:03:00.2")
    _sriov_device = sriovify.PCIDevice("0000:03:00.3")
    _nonpf_device = sriovify.PCIDevice("0000:01:00.0")

    def test___str__(self):
        self.assertEqual(str(self._device), "0000:03:00.1")

    def test_path(self):
        self.assertEqual(
            self._device.path, "/sys/bus/pci/devices/0000:03:00.1"
        )

    def test_subpath(self):
        self.assertEqual(
            self._device.subpath("foobar"),
            "/sys/bus/pci/devices/0000:03:00.1/foobar",
        )

    @mock.patch("os.path.exists", side_effect=pci_exists_helper)
    @mock.patch("os.readlink", side_effect=pci_readlink_helper)
    def test_is_pf_is_vf(self, _readlink, _exists):
        self.assertTrue(self._device.is_pf)
        self.assertFalse(self._device.is_vf)
        self.assertTrue(self._sriov_device.is_vf)
        self.assertFalse(self._sriov_device.is_pf)
        self.assertFalse(self._nonpf_device.is_pf)
        self.assertFalse(self._nonpf_device.is_vf)

    @mock.patch("os.path.exists", side_effect=pci_exists_helper)
    @mock.patch("os.readlink", side_effect=pci_readlink_helper)
    def test_bound(self, _readlink, _exists):
        self.assertTrue(self._device.bound)
        self.assertFalse(self._unbound_device.bound)

    @mock.patch("os.path.exists", side_effect=pci_exists_helper)
    @mock.patch("os.readlink", side_effect=pci_readlink_helper)
    def test_driver(self, _readlink, _exists):
        self.assertEqual(self._device.driver, "mlx5_core")
        self.assertEqual(self._nonpf_device.driver, "igb")

    @mock.patch("os.path.exists", side_effect=pci_exists_helper)
    @mock.patch("os.readlink", side_effect=pci_readlink_helper)
    def test_vf_addrs(self, _readlink, _exists):
        self.assertEqual(
            self._device.vf_addrs, ["0000:03:00.2", "0000:03:00.3"]
        )
        self.assertEqual(self._nonpf_device.vf_addrs, [])
        self.assertEqual(len(self._device.vfs), 2)

    @mock.patch("subprocess.check_output")
    def test_devlink_get(self, _check_output):
        _test_data = {"dev": {"pci/0000:03:00.1": {"test": "data"}}}
        _check_output.return_value = json.dumps(_test_data)
        self.assertEqual(self._device.devlink_get("eswitch"), {"test": "data"})
        _check_output.assert_called_once_with(
            [
                "/sbin/devlink",
                "dev",
                "eswitch",
                "show",
                "pci/0000:03:00.1",
                "--json",
            ]
        )

    @mock.patch("subprocess.check_call")
    def test_devlink_set(self, _check_call):
        self._device.devlink_set("eswitch", "foo", "bar")
        _check_call.assert_called_once_with(
            [
                "/sbin/devlink",
                "dev",
                "eswitch",
                "set",
                "pci/0000:03:00.1",
                "foo",
                "bar",
            ]
        )


EXPECTED_OUTPUT = """0000:01:00.0\t/sys/class/net/eno1\tixgbe\t
0000:01:00.1\t/sys/class/net/eno2\tixgbe\t
0000:03:00.0\t/sys/class/net/enp3s0f0\tmlx5_core\tPF
0000:03:00.1\t/sys/class/net/enp3s0f1\tmlx5_core\tPF
0000:03:00.2\t/sys/class/net/enp3s0f2\tmlx5_core\tVF of /sys/class/net/enp3s0f0
0000:03:00.3\t/sys/class/net/enp3s0f3\tmlx5_core\tVF of /sys/class/net/enp3s0f1
0000:05:00.0\t/sys/class/net/eno3\tigb\t
0000:05:00.1\t/sys/class/net/eno4\tigb\t
0000:82:00.0\t/sys/class/net/enp130s0f0\tixgbe\tPF
0000:82:00.1\t/sys/class/net/enp130s0f1\tixgbe\tPF
"""


class TestCommands(unittest.TestCase):
    @mock.patch("builtins.open", new_callable=mock.mock_open)
    @mock.patch("os.listdir")
    @mock.patch.object(sriovify, "PCIDevice")
    def test_switch(self, _pcidevice, _listdir, _open):
        # NOTE: PF's and VF's
        _listdir.return_value = [
            "0000:01:00.0",
            "0000:03:00.0",
            "0000:03:00.1",
            "0000:03:00.2",
            "0000:03:00.3",
            "0000:03:00.4",
        ]
        mockPCIDeviceVF = mock.MagicMock()
        mockPCIDeviceVF.driver = "mlx5_core"
        mockPCIDeviceVF.is_pf = False
        mockPCIDeviceVF.pci_addr = "0000:03:00.2"
        mockPCIDeviceVF.bound = True
        mockPCIDeviceVF.__str__.return_value = mockPCIDeviceVF.pci_addr

        mockPCIDeviceVF3 = mock.MagicMock()
        mockPCIDeviceVF3.driver = "mlx5_core"
        mockPCIDeviceVF3.is_pf = False
        mockPCIDeviceVF3.pci_addr = "0000:03:00.4"
        mockPCIDeviceVF3.bound = True
        mockPCIDeviceVF3.__str__.return_value = mockPCIDeviceVF3.pci_addr

        mockPCIDeviceVF2 = mock.MagicMock()
        mockPCIDeviceVF2.driver = "mlx5_core"
        mockPCIDeviceVF2.is_pf = False
        mockPCIDeviceVF2.pci_addr = "0000:03:00.3"
        mockPCIDeviceVF2.bound = True
        mockPCIDeviceVF2.__str__.return_value = mockPCIDeviceVF.pci_addr

        # PF with VFs not in switchdev mode
        mockPCIDevicePF = mock.MagicMock()
        mockPCIDevicePF.driver = "mlx5_core"
        mockPCIDevicePF.is_pf = True
        mockPCIDevicePF.vfs = [mockPCIDeviceVF, mockPCIDeviceVF3]
        mockPCIDevicePF.pci_addr = "0000:03:00.0"
        mockPCIDevicePF.devlink_get.return_value = {"mode": "legacy"}
        mockPCIDevicePF.__str__.return_value = mockPCIDevicePF.pci_addr

        # PF already in switchdev mode
        mockPCIDevicePF2 = mock.MagicMock()
        mockPCIDevicePF2.driver = "mlx5_core"
        mockPCIDevicePF2.is_pf = True
        mockPCIDevicePF2.vfs = [mockPCIDeviceVF2]
        mockPCIDevicePF2.pci_addr = "0000:03:00.1"
        mockPCIDevicePF2.devlink_get.return_value = {"mode": "switchdev"}
        mockPCIDevicePF2.__str__.return_value = mockPCIDevicePF2.pci_addr

        # PF with igbxe driver
        mockPCIDevicePFAlt = mock.MagicMock()
        mockPCIDevicePFAlt.driver = "igbxe"
        mockPCIDevicePFAlt.is_pf = True
        mockPCIDevicePFAlt.vfs = []
        mockPCIDevicePFAlt.pci_addr = "0000:01:00.0"
        mockPCIDevicePFAlt.devlink_get.return_value = {"mode": "legacy"}
        mockPCIDevicePFAlt.__str__.return_value = mockPCIDevicePFAlt.pci_addr

        _pcidevice.side_effect = [
            mockPCIDevicePFAlt,
            mockPCIDevicePF,
            mockPCIDevicePF2,
            mockPCIDeviceVF,
            mockPCIDeviceVF2,
            mockPCIDeviceVF3,
        ]

        sriovify.switch()

        mockPCIDevicePF.devlink_set.assert_called_with(
            "eswitch", "mode", "switchdev"
        )

        # NOTE: device already in switchdev mode
        mockPCIDevicePF2.devlink_set.assert_not_called()
        # NOTE: not a mlx5_core driven device
        mockPCIDevicePFAlt.devlink_set.assert_not_called()

        _open.assert_called_with("/sys/bus/pci/drivers/mlx5_core/bind", "wt")
        handle = _open()
        self.assertEqual(
            handle.write.mock_calls,
            [
                mock.call("0000:03:00.2"),
                mock.call("0000:03:00.4"),
                mock.call("0000:03:00.2"),
                mock.call("0000:03:00.4"),
            ],
        )

    @mock.patch("sys.stdout", new_callable=io.StringIO)
    @mock.patch("os.listdir", return_value=NETDEV_DEVICES.keys())
    @mock.patch("os.path.exists", side_effect=netdev_exists_helper)
    @mock.patch("os.readlink", side_effect=netdev_readlink_helper)
    def test_show(self, _readlink, _exists, _listdir, _stdout):
        sriovify.show()
        self.assertEqual(_stdout.getvalue(), EXPECTED_OUTPUT)
