import copy
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xaupy_engine.config_schema import default_profile, validate_profile
from xaupy_engine.mt5_set import (
    SetDocument,
    export_set_document,
    import_set_document,
)


class Mt5SetRoundTripTests(unittest.TestCase):
    def test_utf16_bom_comments_order_unknown_and_optimizer_suffix_survive(self):
        text = (
            "; MT5 preset\r\n"
            "UnknownVendorKey=abc||1||2||3||Y\r\n"
            "DirectionTF=H1||M1||0||H4||Y\r\n"
            "PullbackRSIBuy=45||20||1||80||N\r\n"
            "# keep me\r\n"
        )
        raw = b"\xff\xfe" + text.encode("utf-16-le")
        document = SetDocument.from_bytes(raw)

        self.assertEqual("utf-16-le", document.encoding)
        self.assertTrue(document.bom)
        self.assertEqual("\r\n", document.newline)

        result = import_set_document(document)
        self.assertEqual("H1", result.profile["timeframes"]["direction"])
        self.assertEqual(45.0, result.profile["pullback"]["rsi_buy_level"])
        self.assertIn("UnknownVendorKey", result.unknown_keys)

        result.profile["timeframes"]["direction"] = "H4"
        result.profile["pullback"]["rsi_buy_level"] = 47.5
        exported = export_set_document(result.profile, document)
        output = exported.to_bytes()

        self.assertTrue(output.startswith(b"\xff\xfe"))
        decoded = output[2:].decode("utf-16-le")
        self.assertIn("; MT5 preset\r\n", decoded)
        self.assertIn("UnknownVendorKey=abc||1||2||3||Y", decoded)
        self.assertIn("DirectionTF=H4||M1||0||H4||Y", decoded)
        self.assertIn("PullbackRSIBuy=47.5||20||1||80||N", decoded)
        self.assertLess(decoded.index("UnknownVendorKey"), decoded.index("DirectionTF"))
        self.assertLess(decoded.index("DirectionTF"), decoded.index("PullbackRSIBuy"))

    def test_template_export_does_not_append_missing_fields_by_default(self):
        doc = SetDocument.from_text(
            "; one\nDirectionTF=M30\nUnknown=42\n",
            encoding="utf-8",
        )
        profile = default_profile()
        profile["timeframes"]["direction"] = "H1"
        output = export_set_document(profile, doc)
        self.assertEqual(3, len(output.lines))
        self.assertEqual(
            "; one\nDirectionTF=H1\nUnknown=42\n",
            output.to_text(),
        )

    def test_append_missing_is_explicit(self):
        doc = SetDocument.from_text("DirectionTF=M30\n")
        profile = default_profile()
        output = export_set_document(profile, doc, append_missing=True)
        self.assertGreater(len(output.lines), 100)
        self.assertIn("XAUPY_TriggerTF=M1", output.to_text())

    def test_new_export_is_utf16le_bom_and_full_canonical(self):
        profile = default_profile()
        document = export_set_document(profile)
        payload = document.to_bytes()
        self.assertTrue(payload.startswith(b"\xff\xfe"))
        text = payload[2:].decode("utf-16-le")
        self.assertIn("XAUPY_DirectionTF=M30", text)
        self.assertIn("XAUPY_PullbackTF=M5", text)
        self.assertIn("XAUPY_TriggerTF=M1", text)
        self.assertIn("XAUPY_AllowRealAccount=false", text)

    def test_canonical_export_import_roundtrip_preserves_profile(self):
        profile = default_profile()
        profile["timeframes"]["direction"] = "H1"
        profile["timeframes"]["pullback"] = "M15"
        profile["timeframes"]["trigger"] = "M3"
        profile["pullback"]["rsi_buy_level"] = 45.0
        profile["pullback"]["rsi_sell_level"] = 55.0
        profile["trigger"]["rsi_reversal_delta"] = 2.5
        profile["risk"]["max_lot"] = 0.2

        document = export_set_document(profile)
        imported = import_set_document(SetDocument.from_bytes(document.to_bytes()))
        self.assertEqual([], validate_profile(imported.profile))
        self.assertEqual(profile, imported.profile)

    def test_bad_known_value_does_not_corrupt_profile(self):
        doc = SetDocument.from_text(
            "DirectionTF=M2\n"
            "PullbackRSIBuy=not-a-number\n"
            "UnknownFoo=bar\n"
        )
        result = import_set_document(doc)
        self.assertEqual("M30", result.profile["timeframes"]["direction"])
        self.assertEqual(40.0, result.profile["pullback"]["rsi_buy_level"])
        self.assertIn("DirectionTF", result.unknown_keys)
        self.assertIn("PullbackRSIBuy", result.unknown_keys)
        self.assertIn("UnknownFoo", result.unknown_keys)
        self.assertEqual([], validate_profile(result.profile))

    def test_utf8_bom_and_cp1252_are_detected(self):
        utf8 = SetDocument.from_bytes(b"\xef\xbb\xbfDirectionTF=M30\r\n")
        self.assertEqual("utf-8", utf8.encoding)
        self.assertTrue(utf8.bom)

        cp = SetDocument.from_bytes("Comment=olá\n".encode("cp1252"))
        self.assertEqual("cp1252", cp.encoding)
        self.assertFalse(cp.bom)

    def test_roundtrip_without_changes_is_byte_identical(self):
        text = "; c\r\nUnknown=abc||1||2||3||Y\r\nDirectionTF=M30\r\n"
        raw = b"\xff\xfe" + text.encode("utf-16-le")
        doc = SetDocument.from_bytes(raw)
        self.assertEqual(raw, doc.to_bytes())


if __name__ == "__main__":
    unittest.main()
