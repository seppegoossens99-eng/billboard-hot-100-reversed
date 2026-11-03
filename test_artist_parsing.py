"""Regression tests for credited artist parsing."""
import unittest
from generate_details import main_artist, split_artists

class ArtistParsingTests(unittest.TestCase):
    def test_king_gizzard(self):
        credit = "Justice, Tame Impala, SZA & King Gizzard & The Lizard Wizard"
        self.assertEqual(split_artists(credit), [
            "Justice", "Tame Impala", "SZA", "King Gizzard & The Lizard Wizard"])
        self.assertEqual(main_artist(credit), "Justice")

    def test_other_protected_groups(self):
        self.assertEqual(split_artists("Earth, Wind & Fire & Drake"), ["Earth, Wind & Fire", "Drake"])
        self.assertEqual(split_artists("Tyler, the Creator featuring Kali Uchis"), ["Tyler, the Creator", "Kali Uchis"])

if __name__ == "__main__":
    unittest.main()
