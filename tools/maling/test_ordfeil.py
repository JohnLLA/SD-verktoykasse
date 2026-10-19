#!/usr/bin/env python3
"""Enhetstester: python3 -I tools/maling/test_ordfeil.py"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import malform  # noqa: E402
import ordfeil as o  # noqa: E402


class Norm(unittest.TestCase):
    def test_basis(self):
        self.assertEqual(o.normaliser("Nordmenn er, <ee> trøndere! Æ-Ø-Å 12 %"), "nordmenn er trøndere æ ø å 12")

    def test_stjerne(self):
        self.assertEqual(o.normaliser("*Fredric Helen"), "fredric helen")

    def test_nfc(self):
        self.assertEqual(o.normaliser("å"), "å")


class Wer(unittest.TestCase):
    def test_lik(self):
        r = o.vurder("a b c".split(), "a b c".split())
        self.assertEqual(r["wer"], 0)

    def test_tre_typer(self):
        r = o.vurder("a b c d".split(), "a x c d e".split())
        self.assertEqual((r["subst"], r["slettet"], r["innsatt"]), (1, 0, 1))
        self.assertAlmostEqual(r["wer"], 0.5)

    def test_tom_hyp(self):
        r = o.vurder("a b c".split(), [])
        self.assertEqual(r["wer"], 1.0)
        self.assertEqual(r["slettet"], 3)

    def test_hopp(self):
        ref = "en to tre fire fem seks sju åtte ni ti".split()
        hyp = "en to tre ni ti".split()
        r = o.vurder(ref, hyp, setninger=[(0, 3), (3, 8), (8, 10)])
        self.assertEqual(r["hopp"], 1)
        self.assertEqual(r["hopp_ord"], 5)
        self.assertEqual(r["hoppede_setninger"], 1)
        self.assertEqual(r["setninger"], 3)

    def test_wer_over_en(self):
        r = o.vurder(["a"], "x y z".split())
        self.assertAlmostEqual(r["wer"], 3.0)

    def test_cer(self):
        self.assertAlmostEqual(o.cer("abcd", "abxd"), 0.25)
        self.assertEqual(o.cer("", "abc"), 0.0)

    def test_streng(self):
        self.assertNotEqual(o.ord_streng("Hei,"), o.ord_streng("hei"))


class Malform(unittest.TestCase):
    def test_andel(self):
        self.assertEqual(malform.bokmalsandel("vi kallar heim ikkje"), 0.0)
        self.assertEqual(malform.bokmalsandel("vi kaller hjem ikke"), 1.0)
        self.assertAlmostEqual(malform.bokmalsandel("hjem og heim"), 0.5)
        self.assertIsNone(malform.bokmalsandel("og så mange"))

    def test_ingen_overlapp(self):
        self.assertFalse(malform.BOKMAL & malform.NYNORSK)


if __name__ == "__main__":
    unittest.main()
