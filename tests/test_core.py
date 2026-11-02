import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from video_codec_scanner import format_bitrate, format_duration, metrics, parse_ffprobe


class CoreTests(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(format_duration(3661.25), "01:01:01.250")
        self.assertEqual(format_bitrate(5_000_000), "5,00 Mbit/s")

    def test_ffprobe_normalization_and_metrics(self):
        with tempfile.NamedTemporaryFile(suffix=".mkv") as sample:
            data = {
                "format": {
                    "format_long_name": "Matroska / WebM",
                    "duration": "60.0",
                    "size": "45000000",
                    "bit_rate": "6000000",
                },
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "h264",
                        "codec_long_name": "H.264 / AVC",
                        "profile": "High",
                        "width": 1920,
                        "height": 1080,
                        "display_aspect_ratio": "16:9",
                        "avg_frame_rate": "25/1",
                        "bit_rate": "5500000",
                    },
                    {
                        "codec_type": "audio",
                        "codec_name": "aac",
                        "channels": 2,
                        "sample_rate": "48000",
                        "bit_rate": "192000",
                        "tags": {"language": "deu"},
                    },
                    {
                        "codec_type": "subtitle",
                        "codec_name": "subrip",
                        "tags": {"language": "eng"},
                    },
                ],
            }
            report = parse_ffprobe(Path(sample.name), data)
            self.assertEqual(report.container, "Matroska / WebM")
            self.assertEqual(len(report.videos), 1)
            self.assertEqual(len(report.audios), 1)
            self.assertEqual(len(report.subtitles), 1)
            labels = [row[0] for row in metrics(report)]
            self.assertIn("Bits pro Pixel und Bild", labels)
            self.assertIn("Kompressionsverhältnis (Schätzung)", labels)


if __name__ == "__main__":
    unittest.main()
