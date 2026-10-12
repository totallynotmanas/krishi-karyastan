"""Tests for FIPA-ACL messages, schemas, and message broker."""

import pytest
from krishi_karyastan.core.models import Coordinates, TimeSlot
from krishi_karyastan.protocols.messages import ACLMessage, Performative
from krishi_karyastan.protocols.schemas import SoilDeficiencyAlert, AlertUrgency, IrrigationProposal
from krishi_karyastan.protocols.message_bus import MessageBus


def test_fipa_acl_message_creation_and_reply():
    msg = ACLMessage(
        sender="AgentA",
        receiver="AgentB",
        performative=Performative.CFP,
        content={"action": "REQUEST_WATER_BID"},
        timestamp=1,
    )
    assert msg.message_id.startswith("msg_")
    assert msg.performative == Performative.CFP

    reply = msg.create_reply(
        performative=Performative.PROPOSE,
        content={"bid": 10.0},
        sender="AgentB",
        timestamp=2,
    )
    assert reply.sender == "AgentB"
    assert reply.receiver == "AgentA"
    assert reply.in_reply_to == msg.message_id
    assert reply.conversation_id == msg.conversation_id


def test_soil_deficiency_alert_urgency_levels():
    c = Coordinates(x=2, y=2)
    # Severe deficit
    alert_crit = SoilDeficiencyAlert.create_from_reading(
        coords=c, moisture=12.0, nitrogen=30.0, phosphorus=15.0, potassium=100.0,
        flagged_by="sma", tick=5,
    )
    assert alert_crit.urgency == AlertUrgency.CRITICAL
    assert alert_crit.moisture_deficit_pct == 38.0

    # Mild deficit
    alert_med = SoilDeficiencyAlert.create_from_reading(
        coords=c, moisture=38.0, nitrogen=95.0, phosphorus=35.0, potassium=150.0,
        flagged_by="sma", tick=5,
    )
    assert alert_med.urgency == AlertUrgency.MEDIUM


def test_message_bus_pub_sub_and_broadcast():
    bus = MessageBus()
    bus.register_agent("agent_1")
    bus.register_agent("agent_2")
    bus.register_agent("agent_3")

    bus.subscribe("agent_2", "alerts")
    bus.subscribe("agent_3", "alerts")

    # Broadcast to alerts channel
    msg = ACLMessage(
        sender="agent_1",
        receiver="alerts",
        performative=Performative.INFORM,
        content={"flag": "dry_patch"},
        timestamp=1,
    )
    delivered = bus.publish(msg)
    assert delivered == 2

    inbox2 = bus.receive("agent_2")
    inbox3 = bus.receive("agent_3")
    assert len(inbox2) == 1
    assert len(inbox3) == 1
    assert inbox2[0].content["flag"] == "dry_patch"

    # Direct messaging
    direct_msg = ACLMessage(
        sender="agent_2",
        receiver="agent_1",
        performative=Performative.PROPOSE,
        content={"proposal": "accepted"},
        timestamp=2,
    )
    bus.publish(direct_msg)
    inbox1 = bus.receive("agent_1")
    assert len(inbox1) == 1
    assert inbox1[0].sender == "agent_2"
