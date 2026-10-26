import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from transcript_core import (
    CaptionOption, Cue, TranscriptError, VideoInfo, normalize_youtube_url,
    list_caption_options, parse_subtitles, plain_text, make_srt, make_vtt,
    get_video_info, fetch_subtitles, load_subtitle_file,
)

VID = "e_4YEmG9KyU"

class URLTests(unittest.TestCase):
    def test_valid(self):
        variants = [
            f"https://www.youtube.com/watch?v={VID}&list=PLAYLIST",
            f"https://youtu.be/{VID}?t=123",
            f"https://m.youtube.com/shorts/{VID}",
            f"youtube.com/live/{VID}",
            f"https://www.youtube.com/embed/{VID}",
        ]
        for v in variants:
            with self.subTest(v=v):
                self.assertEqual(normalize_youtube_url(v), f"https://www.youtube.com/watch?v={VID}")

    def test_invalid(self):
        bad = ["", "https://youtube.com.evil.com/watch?v="+VID, "file:///tmp/video", "https://youtube.com/playlist?list=abc", "https://youtube.com/watch?v=abc", "https://youtube.com/watch?v="+VID+"&v="+VID, "https://user:pass@youtube.com/watch?v="+VID, "https://www.youtube.com:444/watch?v="+VID, "https://youtube.com/watch?v="+VID+"\nmalicious"]
        for v in bad:
            with self.subTest(v=v):
                with self.assertRaises(TranscriptError): normalize_youtube_url(v)

class ParseTests(unittest.TestCase):
    def test_srt(self):
        srt = "1\r\n00:00:00,000 --> 00:00:01,500\r\nHallo &amp; willkommen\r\n\r\n2\r\n00:00:01,500 --> 00:00:02,100\r\nGrüße aus Wien\r\n"
        cues = parse_subtitles(srt)
        self.assertEqual(len(cues), 2)
        self.assertEqual(cues[0], Cue(0, 1500, "Hallo & willkommen"))
        self.assertIn("Grüße", plain_text(cues))
        self.assertIn("00:00:01,500 --> 00:00:02,100", make_srt(cues))
        self.assertIn("00:00:01.500 --> 00:00:02.100", make_vtt(cues))

    def test_vtt_markup_rolling(self):
        raw = "WEBVTT\n\nKind: captions\n\n00:00:00.000 --> 00:00:01.000 align:start position:0%\n<c>Guten Morgen</c>\n\n00:00:01.000 --> 00:00:02.000\nGuten Morgen zusammen\n\n00:00:02.000 --> 00:00:03.000\nzusammen alle hier\n"
        cues = parse_subtitles(raw)
        self.assertEqual(plain_text(cues), "Guten Morgen zusammen zusammen alle hier\n")
        self.assertEqual(len(cues), 3)

    def test_vtt_metadata_timestamp_does_not_become_caption(self):
        vtt = ("WEBVTT\n\nNOTE About this file\n00:00:00.000 --> 00:00:01.000\nNot speech\n\n"
               "STYLE\n::cue { color: white }\n00:00:01.000 --> 00:00:02.000\nBad\n\n"
               "REGION\nid:fred\n00:00:02.000 --> 00:00:03.000\nWrong\n\n"
               "00:00:03.000 --> 00:00:04.000\nReally spoken\n")
        result = parse_subtitles(vtt)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].text, "Really spoken")

    def test_metadata_only_is_not_a_transcript(self):
        with self.assertRaises(TranscriptError):
            parse_subtitles("WEBVTT\n\nNOTE\n00:00:00.000 --> 00:00:01.000\nNot speech\n")

    def test_empty(self):
        with self.assertRaises(TranscriptError): parse_subtitles("WEBVTT\nNOTE no captions")

    def test_persian_and_srt_roundtrip(self):
        cues = [Cue(0, 1900, "سلام دنیا"), Cue(2000, 2500, "Grüße")]
        self.assertEqual(parse_subtitles(make_srt(cues)), cues)
        self.assertEqual(parse_subtitles(make_vtt(cues)), cues)

    def test_duplicate_blocks(self):
        self.assertEqual(plain_text([Cue(0,2000,"Hallo Welt"),Cue(1000,3000,"Hallo Welt"),Cue(3000,5000,"Wie geht es")]),"Hallo Welt Wie geht es\n")

    def test_preserve_actual_word_repetition(self):
        cues = [Cue(0,1000,"ja"), Cue(1000,2000,"ja"), Cue(2000,3000,"ich"), Cue(3000,4000,"ich")]
        self.assertEqual(plain_text(cues), "ja ja ich ich\n")

    def test_preserve_sentence_repetition(self):
        cues = [Cue(0,1000,"Nein danke"), Cue(1500,2600,"Nein danke")]
        self.assertEqual(plain_text(cues), "Nein danke Nein danke\n")

    def test_local_file_without_network(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/"sample.vtt"
            p.write_text("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nGrüße سلام\n",encoding="utf-8")
            self.assertEqual(load_subtitle_file(p)[0].text,"Grüße سلام")

    def test_local_file_invalid(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/"sample.txt"
            p.write_text("fake",encoding="utf-8")
            with self.assertRaises(TranscriptError): load_subtitle_file(p)

class AdapterTests(unittest.TestCase):
    def test_caption_options(self):
        opts = list_caption_options({"subtitles":{"en":[{"ext":"vtt"}],"fr":[{"ext":"ttml"}],"de":[{"ext":"srt"}]},"automatic_captions":{"de":[{"ext":"vtt"}],"live_chat":[{"ext":"vtt"}]}})
        self.assertEqual([x.label for x in opts], ["de – Manuell", "de – Automatisch", "en – Manuell"])

    def test_fetch_only_subtitles_options(self):
        calls=[]
        class FakeYDL:
            def __init__(self, opts): self.opts=opts;calls.append(opts)
            def __enter__(self): return self
            def __exit__(self,*args): return None
            def download(self, urls):
                self_urls=urls
                self_file=Path(self.opts['outtmpl'].replace('%(ext)s','en.vtt'))
                self_file.write_text('WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHello!\n',encoding='utf-8')
                return 0
        fake = types.SimpleNamespace(YoutubeDL=FakeYDL)
        info=VideoInfo(VID,'Test',(CaptionOption('en','auto'),))
        with patch.dict(sys.modules,{"yt_dlp":fake}):
            cues=fetch_subtitles(info,info.captions[0])
        self.assertEqual(cues[0].text,'Hello!')
        self.assertTrue(calls[0]['skip_download'])
        self.assertTrue(calls[0]['noplaylist'])
        self.assertFalse(calls[0]['writesubtitles'])
        self.assertTrue(calls[0]['writeautomaticsub'])
        self.assertEqual(calls[0]['subtitleslangs'],['en'])

    def test_wrong_language_does_not_silently_pass(self):
        class FakeYDL:
            def __init__(self, opts): self.opts=opts
            def __enter__(self): return self
            def __exit__(self,*args): return None
            def download(self, urls):
                path=Path(self.opts['outtmpl'].replace('%(ext)s','fr.vtt'))
                path.write_text('WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nBonjour\n', encoding='utf-8')
                return 0
        info = VideoInfo(VID, 'Test', (CaptionOption('de','manual'),))
        with patch.dict(sys.modules, {'yt_dlp':types.SimpleNamespace(YoutubeDL=FakeYDL)}):
            with self.assertRaisesRegex(TranscriptError, 'gewählte Untertitelsprache'):
                fetch_subtitles(info, info.captions[0])

    def test_missing_file_is_error(self):
        class FakeYDL:
            def __init__(self, opts): pass
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def download(self, urls): return 0
        fake=types.SimpleNamespace(YoutubeDL=FakeYDL)
        info=VideoInfo(VID,'No subs',(CaptionOption('de','manual'),))
        with patch.dict(sys.modules,{"yt_dlp":fake}):
            with self.assertRaises(TranscriptError): fetch_subtitles(info,info.captions[0])

    def test_get_video_info(self):
        class FakeYDL:
            def __init__(self, opts): self.opts=opts
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def extract_info(self,url,download=False):
                self.flag=(url,download)
                return {'id':VID,'title':'Hallo','subtitles':{'de':[{'ext':'vtt'}]}}
        with patch.dict(sys.modules,{"yt_dlp":types.SimpleNamespace(YoutubeDL=FakeYDL)}):
            value=get_video_info(f'https://youtu.be/{VID}')
        self.assertEqual(value.title,'Hallo')
        self.assertEqual(value.captions[0].language,'de')

if __name__ == "__main__": unittest.main()
