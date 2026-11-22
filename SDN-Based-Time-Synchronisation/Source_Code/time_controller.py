
from os_ken.base import app_manager
from os_ken.controller import ofp_event

from os_ken.controller.handler import (
    CONFIG_DISPATCHER,
    MAIN_DISPATCHER,
    DEAD_DISPATCHER,
    set_ev_cls
)

from os_ken.ofproto import ofproto_v1_3

from os_ken.lib.packet import packet
from os_ken.lib.packet import ethernet
from os_ken.lib.packet import ether_types

from os_ken.lib import hub

import time

class TimeController(app_manager.OSKenApp):

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    # Monitoring settings
    MONITOR_INTERVAL = 2

    # Congestion thresholds in bits per second
    CONGESTION_THRESHOLD = 600000
    RECOVERY_THRESHOLD = 400000

    # Switch port configuration
    SERVER_PORT = 1
    CLIENT_PORTS = [2, 3]

    # UDP application ports
    SYNC_PORT = 5005
    BACKGROUND_PORT = 5001

    def __init__(self, *args, **kwargs):

        super(TimeController, self).__init__(*args, **kwargs)

        self.mac_to_port = {}

        self.datapaths = {}

        self.previous_stats = {}

        self.congestion_state = {}

        self.logger.info(
            "Dynamic D2 QoS Controller started"
        )

    # --------------------------------------------------
    # INSTALL OR MODIFY OPENFLOW RULES
    # --------------------------------------------------

    def add_flow(
        self,
        datapath,
        priority,
        match,
        actions,
        command=None
    ):

        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        if command is None:
            command = ofproto.OFPFC_ADD

        instructions = [
            parser.OFPInstructionActions(
                ofproto.OFPIT_APPLY_ACTIONS,
                actions
            )
        ]

        mod = parser.OFPFlowMod(
            datapath=datapath,
            command=command,
            priority=priority,
            match=match,
            instructions=instructions
        )

        datapath.send_msg(mod)

    # --------------------------------------------------
    # DYNAMIC QOS POLICY
    # --------------------------------------------------

    def install_traffic_policy(self, datapath, congested):

        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        if congested:

            sync_queue = 1
            mode = "CONGESTION"

        else:

            sync_queue = 0
            mode = "NORMAL"

        # Install rules for h2 and h3
        for input_port in self.CLIENT_PORTS:

            # Synchronization traffic: UDP 5005

            match = parser.OFPMatch(
                in_port=input_port,
                eth_type=0x0800,
                ip_proto=17,
                udp_dst=self.SYNC_PORT
            )

            actions = [
                parser.OFPActionSetQueue(sync_queue),
                parser.OFPActionOutput(self.SERVER_PORT)
            ]

            self.add_flow(
                datapath,
                300,
                match,
                actions,
                command=ofproto.OFPFC_MODIFY_STRICT
            )

            # Background traffic: UDP 5001

            match = parser.OFPMatch(
                in_port=input_port,
                eth_type=0x0800,
                ip_proto=17,
                udp_dst=self.BACKGROUND_PORT
            )

            actions = [
                parser.OFPActionSetQueue(0),
                parser.OFPActionOutput(self.SERVER_PORT)
            ]

            self.add_flow(
                datapath,
                250,
                match,
                actions,
                command=ofproto.OFPFC_MODIFY_STRICT
            )

        self.congestion_state[datapath.id] = congested

        self.logger.info(
            "DYNAMIC POLICY: %s | "
            "Synchronization Queue=%s | Background Queue=0",
            mode,
            sync_queue
        )

    # --------------------------------------------------
    # SERVER REPLY FLOWS
    # --------------------------------------------------

    def add_reply_flows(self, datapath):

        parser = datapath.ofproto_parser

        clients = [
            ("10.0.0.2", 2),
            ("10.0.0.3", 3)
        ]

        for client_ip, client_port in clients:

            match = parser.OFPMatch(
                in_port=self.SERVER_PORT,
                eth_type=0x0800,
                ip_proto=17,
                ipv4_src="10.0.0.1",
                ipv4_dst=client_ip,
                udp_src=self.SYNC_PORT
            )

            actions = [
                parser.OFPActionOutput(client_port)
            ]

            self.add_flow(
                datapath,
                300,
                match,
                actions
            )

    # --------------------------------------------------
    # SWITCH CONNECTION
    # --------------------------------------------------

    @set_ev_cls(
        ofp_event.EventOFPSwitchFeatures,
        CONFIG_DISPATCHER
    )
    def switch_features_handler(self, ev):

        datapath = ev.msg.datapath

        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        dpid = datapath.id

        self.datapaths[dpid] = datapath

        self.mac_to_port.setdefault(dpid, {})

        # Initial normal policy:
        # Synchronization and background traffic use Queue 0.

        for input_port in self.CLIENT_PORTS:

            match = parser.OFPMatch(
                in_port=input_port,
                eth_type=0x0800,
                ip_proto=17,
                udp_dst=self.SYNC_PORT
            )

            actions = [
                parser.OFPActionSetQueue(0),
                parser.OFPActionOutput(self.SERVER_PORT)
            ]

            self.add_flow(
                datapath,
                300,
                match,
                actions
            )

            match = parser.OFPMatch(
                in_port=input_port,
                eth_type=0x0800,
                ip_proto=17,
                udp_dst=self.BACKGROUND_PORT
            )

            actions = [
                parser.OFPActionSetQueue(0),
                parser.OFPActionOutput(self.SERVER_PORT)
            ]

            self.add_flow(
                datapath,
                250,
                match,
                actions
            )

        # Install server reply rules
        self.add_reply_flows(datapath)

        # Table-miss rule
        match = parser.OFPMatch()

        actions = [
            parser.OFPActionOutput(
                ofproto.OFPP_CONTROLLER,
                ofproto.OFPCML_NO_BUFFER
            )
        ]

        self.add_flow(
            datapath,
            0,
            match,
            actions
        )

        self.congestion_state[dpid] = False

        self.logger.info(
            "Switch %s connected. Initial mode: NORMAL",
            dpid
        )

        # Start periodic traffic monitoring
        hub.spawn(
            self.monitor_traffic,
            datapath
        )

    # --------------------------------------------------
    # PERIODIC PORT STATISTICS REQUEST
    # --------------------------------------------------

    def monitor_traffic(self, datapath):

        parser = datapath.ofproto_parser

        ofproto = datapath.ofproto

        while datapath.id in self.datapaths:

            request = parser.OFPPortStatsRequest(
                datapath,
                0,
                self.SERVER_PORT
            )

            datapath.send_msg(request)

            hub.sleep(self.MONITOR_INTERVAL)

    # --------------------------------------------------
    # TRAFFIC RATE CALCULATION AND CONGESTION DETECTION
    # --------------------------------------------------

    @set_ev_cls(
        ofp_event.EventOFPPortStatsReply,
        MAIN_DISPATCHER
    )
    def port_stats_reply_handler(self, ev):

        datapath = ev.msg.datapath

        dpid = datapath.id

        now = time.monotonic()

        for stat in ev.msg.body:

            if stat.port_no != self.SERVER_PORT:
                continue

            current_bytes = stat.tx_bytes

            previous = self.previous_stats.get(dpid)

            self.previous_stats[dpid] = (
                current_bytes,
                now
            )

            # First reading establishes the baseline
            if previous is None:
                continue

            previous_bytes, previous_time = previous

            elapsed = now - previous_time

            byte_difference = (
                current_bytes - previous_bytes
            )

            if elapsed <= 0 or byte_difference < 0:
                continue

            # Calculate outgoing traffic rate
            traffic_rate = (
                byte_difference * 8 / elapsed
            )

            current_mode = self.congestion_state.get(
                dpid,
                False
            )

            self.logger.info(
                "Port %s traffic rate: %.2f kbps | Mode: %s",
                self.SERVER_PORT,
                traffic_rate / 1000,
                "CONGESTION" if current_mode else "NORMAL"
            )

            # Detect congestion
            if (
                not current_mode
                and traffic_rate > self.CONGESTION_THRESHOLD
            ):

                self.logger.warning(
                    "CONGESTION DETECTED: %.2f kbps",
                    traffic_rate / 1000
                )

                self.install_traffic_policy(
                    datapath,
                    True
                )

            # Detect recovery
            elif (
                current_mode
                and traffic_rate < self.RECOVERY_THRESHOLD
            ):

                self.logger.info(
                    "NETWORK RECOVERED: %.2f kbps",
                    traffic_rate / 1000
                )

                self.install_traffic_policy(
                    datapath,
                    False
                )

    # --------------------------------------------------
    # HANDLE UNKNOWN PACKETS
    # --------------------------------------------------

    @set_ev_cls(
        ofp_event.EventOFPPacketIn,
        MAIN_DISPATCHER
    )
    def packet_in_handler(self, ev):

        msg = ev.msg

        datapath = msg.datapath

        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        in_port = msg.match["in_port"]

        pkt = packet.Packet(msg.data)

        eth = pkt.get_protocol(
            ethernet.ethernet
        )

        if eth is None:
            return

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        dpid = datapath.id

        self.mac_to_port.setdefault(dpid, {})

        src = eth.src
        dst = eth.dst

        self.mac_to_port[dpid][src] = in_port

        out_port = self.mac_to_port[dpid].get(
            dst,
            ofproto.OFPP_FLOOD
        )

        actions = [
            parser.OFPActionOutput(out_port)
        ]

        if out_port != ofproto.OFPP_FLOOD:

            match = parser.OFPMatch(
                in_port=in_port,
                eth_dst=dst
            )

            self.add_flow(
                datapath,
                10,
                match,
                actions
            )

        data = None

        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        packet_out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data
        )

        datapath.send_msg(packet_out)

    # --------------------------------------------------
    # SWITCH STATE CHANGE / DISCONNECTION
    # --------------------------------------------------

    @set_ev_cls(
        ofp_event.EventOFPStateChange,
        [MAIN_DISPATCHER, DEAD_DISPATCHER]
    )
    def state_change_handler(self, ev):

        datapath = ev.datapath

        dpid = datapath.id

        if ev.state == MAIN_DISPATCHER:

            self.datapaths[dpid] = datapath

        elif ev.state == DEAD_DISPATCHER:

            self.datapaths.pop(dpid, None)

            self.previous_stats.pop(dpid, None)

            self.congestion_state.pop(dpid, None)

            self.logger.info(
                "Switch %s disconnected",
                dpid
            )
