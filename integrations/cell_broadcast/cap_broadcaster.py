"""
CAP (Common Alerting Protocol) Cell Broadcast Integration

CAP is the international standard (ITU-T X.1303) for emergency alerts.
India's NDMA uses CAP for:
- Cell Broadcast Service (CBS) — reaches all phones without data
- Wireless Emergency Alerts (WEA) — built into every mobile network
- National Emergency Communication System

This module generates valid CAP 1.2 XML alerts and submits them to:
1. NDMA's Cell Broadcast Entity (CBE) API (production)
2. A local mock CBE for demo (prints to console + Kafka)

CAP Alert Structure:
  <alert>
    <identifier>   Unique alert ID
    <sender>       argus@flood.gov.in
    <sent>         ISO datetime
    <status>       Actual / Exercise / System / Test
    <msgType>      Alert / Update / Cancel / Ack
    <scope>        Public / Restricted / Private
    <info>
      <category>   Met (meteorological)
      <event>      Flash Flood Warning
      <urgency>    Immediate / Expected / Future / Past
      <severity>   Extreme / Severe / Moderate / Minor
      <certainty>  Observed / Likely / Possible / Unlikely
      <area>
        <polygon>  WGS84 polygon of warned area
      </area>
"""

from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom
from datetime import datetime
import httpx, hashlib, structlog

logger = structlog.get_logger()

class CAPBroadcaster:
    """
    Generates and broadcasts CAP 1.2 alerts via NDMA Cell Broadcast Entity.

    Alert level mapping (ARGUS → CAP → NDMA color):
    ADVISORY  → Minor,    Future,   Possible  → Green
    WATCH     → Moderate, Expected, Likely     → Yellow
    WARNING   → Severe,   Expected, Likely     → Orange
    EMERGENCY → Extreme,  Immediate, Observed  → Red
    """

    ARGUS_TO_CAP = {
        "ADVISORY":  {"urgency": "Future",    "severity": "Minor",    "certainty": "Possible",
                      "ndma_color": "GREEN",  "ndma_code": "1"},
        "WATCH":     {"urgency": "Expected",  "severity": "Moderate", "certainty": "Likely",
                      "ndma_color": "YELLOW", "ndma_code": "2"},
        "WARNING":   {"urgency": "Expected",  "severity": "Severe",   "certainty": "Likely",
                      "ndma_color": "ORANGE", "ndma_code": "3"},
        "EMERGENCY": {"urgency": "Immediate", "severity": "Extreme",  "certainty": "Observed",
                      "ndma_color": "RED",    "ndma_code": "4"},
    }

    def generate_cap_xml(
        self,
        alert_level: str,
        village_name: str,
        district: str,
        state: str,
        polygon_coords: list[tuple],
        message_english: str,
        message_local: str,
        local_language: str,
        predicted_flood_time: datetime,
        lead_time_minutes: int,
        argus_confidence: float
    ) -> str:
        """
        Generates a valid CAP 1.2 XML alert string.
        Bilingual: English + local language in separate <info> blocks.
        """
        cap = self.ARGUS_TO_CAP.get(alert_level, self.ARGUS_TO_CAP["ADVISORY"])
        alert_id = f"ARGUS-{district.upper()}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

        root = Element("alert", xmlns="urn:oasis:names:tc:emergency:cap:1.2")

        SubElement(root, "identifier").text = alert_id
        SubElement(root, "sender").text     = "argus@floodwarning.gov.in"
        SubElement(root, "sent").text       = datetime.utcnow().isoformat() + "+05:30"
        SubElement(root, "status").text     = "Actual"
        SubElement(root, "msgType").text    = "Alert"
        SubElement(root, "scope").text      = "Public"

        # English info block
        info_en = SubElement(root, "info")
        SubElement(info_en, "language").text  = "en-IN"
        SubElement(info_en, "category").text  = "Met"
        SubElement(info_en, "event").text     = "Flash Flood Warning"
        SubElement(info_en, "urgency").text   = cap["urgency"]
        SubElement(info_en, "severity").text  = cap["severity"]
        SubElement(info_en, "certainty").text = cap["certainty"]
        SubElement(info_en, "effective").text = datetime.utcnow().isoformat() + "+05:30"
        SubElement(info_en, "onset").text     = predicted_flood_time.isoformat() + "+05:30"
        SubElement(info_en, "expires").text   = (predicted_flood_time).isoformat() + "+05:30"
        SubElement(info_en, "headline").text  = \
            f"ARGUS ALERT: {alert_level} — {village_name}, {district}"
        SubElement(info_en, "description").text = message_english
        SubElement(info_en, "instruction").text = \
            f"Evacuate immediately. Lead time: {lead_time_minutes} minutes. " \
            f"AI confidence: {argus_confidence*100:.0f}%."

        # Parameters: ARGUS-specific metadata
        for name, val in [
            ("ARGUS_LeadTimeMinutes",  str(lead_time_minutes)),
            ("ARGUS_Confidence",       f"{argus_confidence:.2f}"),
            ("ARGUS_NDMAColor",        cap["ndma_color"]),
            ("ARGUS_NDMACode",         cap["ndma_code"]),
        ]:
            param = SubElement(info_en, "parameter")
            SubElement(param, "valueName").text = name
            SubElement(param, "value").text = val

        # Geographic area
        area = SubElement(info_en, "area")
        SubElement(area, "areaDesc").text = f"{village_name}, {district}, {state}"
        if polygon_coords:
            poly_str = " ".join(f"{lat},{lon}" for lat, lon in polygon_coords)
            SubElement(area, "polygon").text = poly_str

        # Local language info block
        if local_language and message_local:
            info_local = SubElement(root, "info")
            SubElement(info_local, "language").text  = local_language
            SubElement(info_local, "category").text  = "Met"
            SubElement(info_local, "event").text     = "Flash Flood Warning"
            SubElement(info_local, "urgency").text   = cap["urgency"]
            SubElement(info_local, "severity").text  = cap["severity"]
            SubElement(info_local, "certainty").text = cap["certainty"]
            SubElement(info_local, "description").text = message_local

        # Pretty-print XML
        xml_str = tostring(root, encoding="unicode")
        return minidom.parseString(xml_str).toprettyxml(indent="  ")

    async def broadcast(self, cap_xml: str, basin_id: str) -> dict:
        """
        Submits CAP XML to NDMA's Cell Broadcast Entity.
        Falls back to mock broadcast for demo/testing.
        """
        NDMA_CBE_URL = "https://cbs.ndma.gov.in/api/v1/alert"   # Production
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(
                    NDMA_CBE_URL,
                    content=cap_xml,
                    headers={
                        "Content-Type": "application/cap+xml",
                        "X-ARGUS-Token": self._get_ndma_token()
                    }
                )
            return {
                "status": "BROADCAST",
                "channel": "NDMA_CELL_BROADCAST",
                "message_id": r.json().get("messageId"),
                "estimated_reach": "All mobile phones in alert polygon"
            }
        except Exception as e:
            logger.warning(f"NDMA CBE unavailable ({e}). Using demo broadcast.")
            return self._mock_broadcast(cap_xml, basin_id)

    def _get_ndma_token(self) -> str:
        """Derive NDMA API token (placeholder for production key management)."""
        import os
        return os.getenv("NDMA_CBE_TOKEN", "demo-token-argus")

    def _mock_broadcast(self, cap_xml: str, basin_id: str) -> dict:
        """Demo mode: logs the CAP XML and publishes to Kafka."""
        logger.info("MOCK Cell Broadcast", basin_id=basin_id)
        print("\n" + "="*60)
        print("CELL BROADCAST ISSUED (DEMO MODE)")
        print("="*60)
        print(cap_xml[:500] + "...")
        print("="*60 + "\n")
        return {
            "status": "MOCK_BROADCAST",
            "channel": "DEMO_CONSOLE",
            "cap_preview": cap_xml[:200]
        }
