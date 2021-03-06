# -*- coding: utf-8 -*-
# Copyright (C) 2016  Fabio Falcinelli
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
import os
import socket
import threading
import unittest
from binascii import hexlify

import pytest
from pydivert.enum import Param, Defaults
from pydivert.tests import FakeTCPServerIPv4, EchoUpperTCPHandler, FakeTCPClient, random_free_port, FakeUDPServer, \
    EchoUpperUDPHandler, FakeUDPClient, FakeTCPServerIPv6
from pydivert.windivert import Handle, WinDivert, DEFAULT_DLL_PATH

__author__ = 'fabio'


class BaseTestCase(unittest.TestCase):
    """
    A base test case to take driver version into account.
    Tests the basic operations like registering the driver.
    """

    def tearDown(self):
        pass

    def test_register(self):
        """
        Tests DLL registration
        """
        d = WinDivert().register()
        assert d.is_registered()
        assert os.path.abspath(d.dll_path) == DEFAULT_DLL_PATH

    def test_load_ok(self):
        """
        Tests DLL loading with a correct path
        """
        try:
            d = WinDivert()
            assert os.path.abspath(d.get_reference()._name) == DEFAULT_DLL_PATH
        except WindowsError as e:
            self.fail("WinDivert() constructor raised %s" % e)

    def test_open_handle(self):
        """
        Tests the open_handle method.
        """
        # with cd(os.path.dirname(self.dll_path)):
        handle = WinDivert().open_handle(filter="tcp.DstPort == 23")
        assert isinstance(handle, Handle)
        assert handle.is_opened
        handle.close()
        assert not handle.is_opened

    def test_load_invalid_path(self):
        """
        Tests DLL loading with an invalid path
        """
        with pytest.raises(ValueError):
            WinDivert("invalid_path")


class WinDivertTestCase(BaseTestCase):
    """
    Tests loading from registry, opening handles and functions not requiring network traffic
    """

    def setUp(self):
        super(WinDivertTestCase, self).setUp()
        WinDivert().register()
        # self.dll_path = os.path.join(self.driver_dir, "WinDivert.dll")

    def test_load_already_registered(self):
        """
        Tests WinDivert loading from the default path (DLLs dir inside python's home).
        This assumes the driver has been previously registered
        """
        try:
            WinDivert()
        except WindowsError as e:
            self.fail("WinDivert() constructor raised %s" % e)

    def test_construct_handle(self):
        """
        Tests constructing an handle from a WinDivert instance
        """
        driver = WinDivert()
        handle = Handle(driver, filter="tcp.DstPort == 23", priority=1000)
        assert isinstance(handle, Handle)
        assert not handle.is_opened

    def test_implicit_construct_handle(self):
        """
        Tests constructing an handle without passing a WinDivert instance
        """
        handle = Handle(filter="tcp.DstPort == 23", priority=1000)
        assert isinstance(handle, Handle)
        assert not handle.is_opened

    def test_handle_invalid(self):
        """
        Tests constructing an handle from a WinDivert instance
        """
        handle = Handle(filter="tcp.DstPort == 23", priority=1000)
        # The handle is not opened so we expect an error
        self.assertRaises(WindowsError, handle.close)

    def test_context_manager(self):
        """
        Tests usage of an Handle as a context manager
        """
        with Handle(filter="tcp.DstPort == 23", priority=1000) as filter0:
            assert str(filter0._handle) != "-1"

    def test_queue_time_range(self):
        """
        Tests setting the minimum value for queue time.
        From docs: 128 < default 512 < 2048
        """
        with Handle(filter="tcp.DstPort == 23", priority=1000) as filter0:
            # TODO: this range should have a proper default representation

            def_range = (128, 512, 2048)
            for value in def_range:
                filter0.set_param(Param.QUEUE_TIME, value)
                assert value == filter0.get_param(Param.QUEUE_TIME)

    def test_queue_len_range(self):
        """
        Tests setting the minimum value for queue length.
        From docs: 1< default 512 <8192
        """
        with Handle(filter="tcp.DstPort == 23", priority=1000) as filter0:
            # TODO: this range should have a proper default representation
            for value in (1, 512, 8192):
                filter0.set_param(Param.QUEUE_LEN, value)
                assert value == filter0.get_param(Param.QUEUE_LEN)

    def test_parse_packet_raise_exc(self):
        """
        Tests the parsing packet function to raise an exception when invoked with wrong number of arguments
        """
        driver = WinDivert().register()
        with pytest.raises(ValueError):
            driver.parse_packet("", "", "")


class WinDivertTCPDataCaptureTestCase(BaseTestCase):
    """
    Tests capturing TCP traffic with payload
    """

    def setUp(self):
        super(WinDivertTCPDataCaptureTestCase, self).setUp()
        # Initialize the fake tcp server
        self.server = FakeTCPServerIPv4(("127.0.0.1", 0), EchoUpperTCPHandler)
        filter = "outbound and tcp.DstPort == %d and tcp.PayloadLength > 0" % self.server.server_address[1]
        self.driver = WinDivert()
        self.driver.register()

        self.handle = self.driver.open_handle(filter=filter)

        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.start()

        # Initialize the fake tcp client
        self.text = "Hello World!"
        self.client = FakeTCPClient(self.server.server_address, self.text.encode("UTF-8"))
        self.client_thread = threading.Thread(target=self.client.send)
        self.client_thread.start()

    def test_packet_metadata(self):
        """
        Tests if metadata is right
        """
        raw_packet, metadata = self.handle.recv()
        assert metadata.is_outbound()
        assert metadata.is_loopback()

    def test_pass_through_tuple(self):
        """
        Tests receiving and resending data
        """
        self.handle.send(self.handle.recv())
        self.client_thread.join(timeout=10)
        assert self.text.upper() == self.client.response.decode()

    def test_pass_through_no_tuple(self):
        """
        Tests receiving and resending data. Sends using 2 arguments instead of tuple
        """
        raw_packet, meta = self.handle.recv()
        self.handle.send(raw_packet, meta)
        self.client_thread.join(timeout=10)
        assert self.text.upper() == self.client.response.decode()

    def test_pass_through_packet(self):
        """
        Tests receiving and resending data. Sends using an higher level packet object
        """
        self.handle.send(self.handle.receive())
        self.client_thread.join(timeout=10)
        assert self.text.upper() == self.client.response.decode()

    def test_parse_packet(self):
        """
        Tests parsing packets to intercept the payload
        """
        raw_packet, metadata = self.handle.recv()
        packet = self.driver.parse_packet(raw_packet)
        assert (packet.dst_addr, packet.dst_port) == self.server.server_address
        assert self.text.encode() == packet.payload

    def test_parse_packet_meta(self):
        """
        Tests parsing packets to intercept the payload and store meta in result
        """
        raw_packet, metadata = self.handle.recv()
        packet = self.driver.parse_packet(raw_packet, metadata)
        assert (packet.dst_addr, packet.dst_port) == self.server.server_address
        assert self.text.encode() == packet.payload
        assert packet.meta == metadata

    def test_dump_data(self):
        """
        Tests receiving, print and resending data
        """
        raw_packet, metadata = self.handle.recv()
        packet = self.handle.driver.parse_packet(raw_packet)
        assert raw_packet[len(packet.payload) * -1:] == packet.raw[len(packet.payload) * -1:]
        self.handle.send((raw_packet, metadata))
        self.client_thread.join(timeout=10)
        assert self.text.upper() == self.client.response.decode()

    def test_raw_packet_from_captured(self):
        """
        Tests reconstructing raw packet from a captured one
        """
        raw_packet1, metadata = self.handle.recv()
        packet = self.handle.driver.parse_packet(raw_packet1)
        raw_packet2 = packet.raw
        assert hexlify(raw_packet1) == hexlify(raw_packet2)

    def test_raw_packet_len(self):
        """
        Tests reconstructing raw packet from a captured and modified one
        """
        raw_packet1, metadata = self.handle.recv()
        packet1 = self.handle.driver.parse_packet(raw_packet1)
        packet1.dst_port = 80
        packet1.dst_addr = "10.10.10.10"
        raw_packet2 = packet1.raw
        assert len(raw_packet1) == len(raw_packet2)

    def test_packet_checksum(self):
        """
        Tests checksum without changes
        """
        raw_packet1, metadata = self.handle.recv()
        raw_packet2 = self.handle.driver.calc_checksums(raw_packet1)
        assert hexlify(raw_packet1) == hexlify(raw_packet2)

    def test_packet_checksum_recalc(self):
        """
        Tests checksum with changes
        """
        raw_packet1, metadata = self.handle.recv()
        packet = self.handle.driver.parse_packet(raw_packet1)
        packet.dst_port = 80
        packet.dst_addr = "10.10.10.10"
        raw_packet2 = self.handle.driver.calc_checksums(packet.raw)
        assert hexlify(raw_packet1) != hexlify(raw_packet2)

    def test_packet_reconstruct_checksummed(self):
        """
        Tests reconstruction of a packet after checksum calculation
        """
        raw_packet1, metadata = self.handle.recv()
        packet1 = self.handle.driver.parse_packet(raw_packet1)
        packet1.dst_port = 80
        packet1.dst_addr = "10.10.10.10"
        raw_packet2 = self.handle.driver.calc_checksums(packet1.raw)
        packet2 = self.handle.driver.parse_packet(raw_packet2)
        assert packet1.dst_port == packet2.dst_port
        assert packet1.dst_addr == packet2.dst_addr
        assert hexlify(raw_packet1) != hexlify(raw_packet2)
        assert len(raw_packet1) == len(packet2.raw)

    def test_packet_to_string(self):
        """
        Tests string conversions
        """
        packet = self.handle.receive()
        assert str(packet.tcp_hdr) in str(packet)
        assert str(packet.ipv4_hdr) in str(packet)
        assert packet.tcp_hdr.raw.decode() == repr(packet.tcp_hdr)
        self.handle.send(packet)

    def test_packet_repr(self):
        """
        Tests repr conversion
        """
        packet = self.handle.receive()
        assert repr(packet) == hexlify(packet.raw).decode()
        self.handle.send(packet)

    def test_modify_address(self):
        """
        Tests address changing
        """
        packet = self.handle.receive()
        current = packet.ipv4_hdr.DstAddr
        packet.dst_addr = "10.0.2.15"
        assert packet.ipv4_hdr.DstAddr == 251789322
        packet.ipv4_hdr.DstAddr = current
        assert packet.dst_addr == "127.0.0.1"
        self.handle.send(packet)

    def test_modify_port(self):
        """
        Tests port changing
        """
        packet = self.handle.receive()
        current = packet.tcp_hdr.DstPort
        packet.dst_port = 23
        assert packet.tcp_hdr.DstPort == 5888
        packet.tcp_hdr.DstPort = current
        assert packet.dst_port == self.server.server_address[1]
        self.handle.send(packet)

    def test_send_wrong_args(self):
        """
        Tests send with wrong number of arguments
        """
        packet = self.handle.receive()
        with pytest.raises(ValueError):
            self.handle.send("test")

    def tearDown(self):
        try:
            self.handle.close()
        except Exception as e:
            pass
        self.server.shutdown()
        self.server.server_close()
        super(WinDivertTCPDataCaptureTestCase, self).tearDown()


class WinDivertTCPIPv4TestCase(BaseTestCase):
    """
    Tests on the fly capturing and injecting TCP/IPv4 traffic
    """

    def setUp(self):
        super(WinDivertTCPIPv4TestCase, self).setUp()
        # Initialize the fake tcp server
        self.server = FakeTCPServerIPv4(("127.0.0.1", 0),
                                        EchoUpperTCPHandler)
        self.driver = WinDivert()

        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.start()

    def test_syn_tcp_options(self):
        """
        Tests the right capturing of tcp options field
        """
        text = "Hello World!"
        client = FakeTCPClient(self.server.server_address, text.encode("UTF-8"))
        client_thread = threading.Thread(target=client.send)

        with Handle(filter="tcp.DstPort == %d" % self.server.server_address[1]) as handle:
            client_thread.start()
            packet = handle.receive()
            assert packet.tcp_hdr.Syn == 1
            assert hexlify(packet.tcp_hdr.Options) == b"0204ffd70103030801010402"
        client_thread.join(timeout=10)

    def test_modify_tcp_payload(self):
        """
        Tests injection of a TCP packet with modified payload
        """
        text = "Hello world! ZZZZ"
        new_text = "Hello World!"
        # Initialize the fake tcp client
        client = FakeTCPClient(self.server.server_address, text.encode("UTF-8"))
        client_thread = threading.Thread(target=client.send)

        filter_ = "outbound and tcp.DstPort == %s and tcp.PayloadLength > 0" % self.server.server_address[1]
        with Handle(filter=filter_) as handle:
            client_thread.start()

            raw_packet, metadata = handle.recv()

            if metadata.is_outbound():
                packet = handle.driver.parse_packet(raw_packet)
                assert text.encode("UTF-8") == packet.payload
                packet.payload = new_text.encode("UTF-8")
                raw_packet = packet.raw

            handle.send((raw_packet, metadata))
            client_thread.join(timeout=10)
            assert new_text.upper() == client.response.decode()

    def test_modify_tcp_header(self):
        """
        Tests injection of a packet with a modified tcp header
        """
        fake_port = random_free_port()
        srv_port = self.server.server_address[1]
        text = "Hello World!"
        client = FakeTCPClient(("127.0.0.1", fake_port), text.encode("UTF-8"))
        client_thread = threading.Thread(target=client.send)

        f = "tcp.DstPort == %d or tcp.SrcPort == %d" % (fake_port, srv_port)
        with Handle(filter=f, priority=1000) as handle:
            # Initialize the fake tcp client
            client_thread.start()
            while True:
                raw_packet, meta = handle.recv()
                packet = handle.driver.parse_packet(raw_packet)

                if meta.is_outbound():
                    if packet.dst_port == fake_port:
                        packet.dst_port = srv_port
                    if packet.src_port == srv_port:
                        packet.src_port = fake_port
                packet = handle.driver.update_packet_checksums(packet)

                handle.send((packet.raw, meta))
                if hasattr(client, "response") and client.response:
                    break
            client_thread.join(timeout=10)
            assert text.upper() == client.response.decode()

    def test_modify_tcp_header_shortcut(self):
        """
        Tests injection of a packet with a modified tcp header using shortcutted send
        """
        fake_port = random_free_port()
        srv_port = self.server.server_address[1]
        text = "Hello World!"
        client = FakeTCPClient(("127.0.0.1", fake_port), text.encode("UTF-8"))
        client_thread = threading.Thread(target=client.send)

        f = "tcp.DstPort == %d or tcp.SrcPort == %d" % (fake_port, srv_port)
        with Handle(filter=f, priority=1000) as handle:
            # Initialize the fake tcp client
            client_thread.start()
            while True:
                packet = handle.receive()

                if packet.meta.is_outbound():
                    if packet.dst_port == fake_port:
                        packet.dst_port = srv_port
                    if packet.src_port == srv_port:
                        packet.src_port = fake_port

                handle.send(packet)
                if hasattr(client, "response") and client.response:
                    break
            client_thread.join(timeout=10)
            assert text.upper() == client.response.decode()

    @pytest.mark.skip(reason=".recv() is not guaranteed to get all content, this test is flaky")
    def test_pass_through_mtu_size(self):
        """
        Tests sending a packet bigger than mtu
        """
        srv_port = self.server.server_address[1]
        text = b"#" * (Defaults.PACKET_BUFFER_SIZE + 1)
        client = FakeTCPClient(("127.0.0.1", srv_port), text)
        client_thread = threading.Thread(target=client.send)

        f = "tcp.DstPort == {0} or tcp.SrcPort == {0} and tcp.PayloadLength > 0".format(srv_port)
        with Handle(filter=f, priority=1000) as handle:
            # Initialize the fake tcp client
            client_thread.start()
            while True:
                handle.send(handle.receive())
                if hasattr(client, "response") and client.response:
                    break
            client_thread.join(timeout=10)
            assert text == client.response

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super(WinDivertTCPIPv4TestCase, self).tearDown()


class WinDivertTCPIPv6TestCase(BaseTestCase):
    """
    Tests on the fly capturing and injecting TCP/IPv6 traffic
    """

    def setUp(self):
        super(WinDivertTCPIPv6TestCase, self).setUp()
        # Initialize the fake tcp server
        self.server = FakeTCPServerIPv6(("::1", 0), EchoUpperTCPHandler)
        WinDivert().register()

        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.start()

    def test_syn_tcp_options(self):
        """
        Tests the right capturing of tcp options field
        """
        text = "Hello World!"
        client = FakeTCPClient(self.server.server_address, text.encode("UTF-8"), ipv6=True)
        client_thread = threading.Thread(target=client.send)

        with Handle(filter="tcp.DstPort == %d" % self.server.server_address[1]) as handle:
            client_thread.start()
            packet = handle.receive()
            assert packet.tcp_hdr.Syn == 1
            assert hexlify(packet.tcp_hdr.Options) == b"0204ffc30103030801010402"

    def test_pass_through(self):
        """
        Tests capture and reinjection of data
        """
        srv_port = self.server.server_address[1]
        text = "Hello World!"
        client = FakeTCPClient(self.server.server_address, text.encode("UTF-8"), ipv6=True)
        client_thread = threading.Thread(target=client.send)

        with Handle(filter="tcp.DstPort == %d and tcp.PayloadLength > 0" % srv_port) as handle:
            client_thread.start()
            handle.send(handle.receive())

        client_thread.join(timeout=10)
        assert text.upper() == client.response.decode()

    def test_modify_tcp_payload(self):
        """
        Tests injection of a TCP packet with modified payload
        """
        text = "Hello world! ZZZZ"
        new_text = "Hello World!"
        # Initialize the fake tcp client
        client = FakeTCPClient(self.server.server_address, text.encode("UTF-8"), ipv6=True)
        client_thread = threading.Thread(target=client.send)
        f = "outbound and tcp.DstPort == %s and tcp.PayloadLength > 0" % self.server.server_address[1]
        with Handle(filter=f) as handle:
            client_thread.start()
            raw_packet, metadata = handle.recv()

            if metadata.is_outbound():
                packet = handle.driver.parse_packet(raw_packet)
                assert text.encode("UTF-8") == packet.payload
                packet.payload = new_text.encode("UTF-8")
                raw_packet = packet.raw

            handle.send((raw_packet, metadata))
            client_thread.join(timeout=10)
            assert new_text.upper() == client.response.decode()

    # def test_modify_tcp_header(self):
    #     """
    #     Tests injection of a packet with a modified tcp header
    #     """
    #     fake_port = random_free_port(family=socket.AF_INET6)
    #     srv_port = self.server.server_address[1]
    #     text = "Hello World!"
    #     # Initialize the fake tcp client
    #     client = FakeTCPClient(("::1", fake_port), text, ipv6=True)
    #     client_thread = threading.Thread(target=client.send)
    #
    #     f = "tcp.DstPort == {0} or tcp.SrcPort == {1}".format(fake_port, srv_port)
    #     with Handle(filter=f) as handle:
    #
    #         client_thread.start()
    #         while True:
    #             packet = handle.receive()
    #             print(packet)
    #             #With loopback interface it seems each packet flow is outbound
    #             if packet.dst_port == fake_port:
    #                 packet.dst_port = srv_port
    #             if packet.src_port == srv_port:
    #                 packet.src_port = fake_port
    #             print(srv_port)
    #             print(packet)
    #             handle.send(packet)
    #             if hasattr(client, "response") and client.response:
    #                 break
    #         client_thread.join(timeout=10)
    #         assert text.upper() == client.response

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super(WinDivertTCPIPv6TestCase, self).tearDown()


class WinDivertUDPTestCase(BaseTestCase):
    def setUp(self):
        super(WinDivertUDPTestCase, self).setUp()
        # Initialize the fake tcp server
        self.server = FakeUDPServer(("127.0.0.1", 0), EchoUpperUDPHandler)
        self.driver = WinDivert()

        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.start()

    def test_modify_udp_payload(self):
        """
        Tests injection of a UDP packet with modified payload
        """
        text = "Hello World!"
        client = FakeUDPClient(("127.0.0.1", self.server.server_address[1]), text.encode("UTF-8"))
        client_thread = threading.Thread(target=client.send)
        filter_ = "outbound and udp.DstPort == %s" % self.server.server_address[1]
        with Handle(filter=filter_) as handle:
            client_thread.start()

            packet = handle.receive()
            assert text.encode("UTF-8") == packet.payload
            handle.send(packet)

            client_thread.join(timeout=10)
            assert text.upper() == client.response.decode()

    def test_modify_udp_header(self):
        """
        Tests injection of a packet with a modified udp header
        """
        fake_port = random_free_port()
        srv_port = self.server.server_address[1]
        text = "Hello World!"
        client = FakeUDPClient(("127.0.0.1", fake_port), text.encode("UTF-8"))
        client_thread = threading.Thread(target=client.send)

        f = "udp.DstPort == %d or udp.SrcPort == %d" % (fake_port, srv_port)
        with Handle(filter=f, priority=1000) as handle:
            # Initialize the fake tcp client
            client_thread.start()

            for i in range(2):
                packet = handle.receive()
                if packet.meta.is_outbound():
                    if packet.dst_port == fake_port:
                        packet.dst_port = srv_port
                    if packet.src_port == srv_port:
                        packet.src_port = fake_port

                handle.send(packet)

            client_thread.join(timeout=10)
            assert text.upper() == client.response.decode()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super(WinDivertUDPTestCase, self).tearDown()


class WinDivertExternalInterfaceTestCase(BaseTestCase):
    def setUp(self):
        super(WinDivertExternalInterfaceTestCase, self).setUp()
        # Initialize the fake tcp server
        self.server = FakeTCPServerIPv4((socket.gethostbyname(socket.gethostname()), 0),
                                        EchoUpperTCPHandler)
        WinDivert().register()

        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.start()

    def test_modify_tcp_header_shortcut(self):
        """
        Tests injection of a packet with a modified tcp header using shortcutted send
        """
        fake_port = random_free_port()
        fake_addr = "10.10.10.10"
        srv_port = self.server.server_address[1]
        srv_addr = self.server.server_address[0]
        text = b"Hello World!"
        client = FakeTCPClient((fake_addr, fake_port), text)
        client_thread = threading.Thread(target=client.send)

        f = "tcp.DstPort == %d or tcp.SrcPort == %d" % (fake_port, srv_port)
        with Handle(filter=f, priority=1000) as handle:
            # Initialize the fake tcp client
            client_thread.start()
            while True:
                packet = handle.receive()

                if packet.meta.is_outbound():
                    if packet.dst_port == fake_port:
                        packet.dst_port = srv_port
                        packet.dst_addr = srv_addr
                    if packet.src_port == srv_port:
                        packet.src_port = fake_port
                        packet.src_addr = fake_addr

                handle.send(packet)
                if hasattr(client, "response") and client.response:
                    break
            client_thread.join(timeout=10)
            assert text.upper() == client.response

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super(WinDivertExternalInterfaceTestCase, self).tearDown()


class WinDivertAsyncTestCase(BaseTestCase):
    def setUp(self):
        super(WinDivertAsyncTestCase, self).setUp()
        # Initialize the fake tcp server
        self.server = FakeTCPServerIPv4(("127.0.0.1", 0), EchoUpperTCPHandler)
        filter = "outbound and tcp.DstPort == %d and tcp.PayloadLength > 0" % self.server.server_address[1]
        self.driver = WinDivert()
        self.driver.register()

        self.handle = self.driver.open_handle(filter=filter)

        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.start()

        # Initialize the fake tcp client
        self.text = "Hello World!"
        self.client = FakeTCPClient(self.server.server_address, self.text.encode("UTF-8"))
        self.client_thread = threading.Thread(target=self.client.send)
        self.client_thread.start()

    def test_async_pass_through(self):
        """

        """

        def callback(*args):
            self.handle._send_async(*args)

        for future in self.handle._receive_async(callback=callback):
            if not future.is_complete():
                pass
            else:
                break
        self.client_thread.join(timeout=10)
        assert self.text.upper() == self.client.response.decode()

    def tearDown(self):
        try:
            self.handle.close()
        except:
            pass
        self.server.shutdown()
        self.server.server_close()
        super(WinDivertAsyncTestCase, self).tearDown()
