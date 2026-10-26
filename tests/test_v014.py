"""v0.1.4 regression tests, deliberately offline/synthetic."""
import tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import transcript_core as t


class RegressionV014(unittest.TestCase):
    def test_rolling_vtt_with_blank_payload_line(self):
        vtt = ("WEBVTT\nKind: captions\nLanguage: de\n\n"
          "00:00:00.160 --> 00:00:02.869 align:start\n \nheute<00:00:00.480><c> sprechen</c><00:00:00.680><c> wir</c><00:00:00.880><c> über</c>\n\n"
          "00:00:02.869 --> 00:00:02.879\nheute sprechen wir über\n\n"
          "00:00:02.879 --> 00:00:05.910\nheute sprechen wir über\ndas<00:00:03.360><c> Wetter</c>\n\n"
          "00:00:05.910 --> 00:00:05.920\ndas Wetter\n\n"
          "00:00:05.920 --> 00:00:08.000\ndas Wetter\nund<00:00:06.300><c> den</c><00:00:06.500><c> Regen</c>\n\n"
          "00:00:08.000 --> 00:00:08.010\nund den Regen\n")
        cues=t.parse_subtitles(vtt)
        self.assertEqual(len(cues),6)
        self.assertEqual(t.plain_text(cues),"heute sprechen wir über das Wetter und den Regen\n")

    def test_zero_duration_preserves_words(self):
        cues=t.parse_subtitles("1\n00:00:01,000 --> 00:00:01,000\nWichtig\n")
        self.assertEqual(cues,[t.Cue(1000,1001,"Wichtig")])

    def test_invalid_negative_cue(self):
        with self.assertRaisesRegex(t.TranscriptError,"rückwärts"):
            t.parse_subtitles("00:00:02.000 --> 00:00:01.000\nWichtig")

    def test_cp1252_and_utf16_offline(self):
        with tempfile.TemporaryDirectory() as d:
            for encoding in ('cp1252','utf-16'):
                with self.subTest(encoding=encoding):
                    p=Path(d)/'foo.srt';p.write_bytes("1\n00:00:00,000 --> 00:00:01,000\nGrüße\n".encode(encoding))
                    cues, desc=t.load_subtitle_file_with_encoding(p)
                    self.assertEqual(cues[0].text,"Grüße")
                    self.assertIn('UTF-16' if encoding=='utf-16' else 'Windows-1252',desc)

    def test_roundtrip_entities(self):
        c=[t.Cue(0,1000,"A & B <C> 1 < 2 / سلام")]
        self.assertEqual(t.parse_subtitles(t.make_srt(c)),c)
        self.assertEqual(t.parse_subtitles(t.make_vtt(c)),c)

    def test_missing_separator_no_merged_cue_id(self):
        c=t.parse_subtitles("1\n00:00:00,000 --> 00:00:01,000\nHallo\n2\n00:00:01,000 --> 00:00:02,000\nWelt\n")
        self.assertEqual([x.text for x in c],["Hallo","Welt"])

    def test_multiline_srt_preserves_linebreak(self):
        c=t.parse_subtitles("1\n00:00:00,000 --> 00:00:01,000\n- Kommst du?\n- Ja.\n")
        self.assertIn("\n- Ja.",t.make_srt(c))
        self.assertEqual(t.parse_subtitles(t.make_srt(c)),c)

    def test_original_preferred_over_machine_translation(self):
        f=lambda q:[{'ext':'vtt','url':'https://www.youtube.com/api/timedtext?lang=en'+q}]
        opts=t.list_caption_options({'automatic_captions':{'de':f('&tlang=de'),'en-orig':f(''),'fr':f('&tlang=fr')}})
        self.assertEqual(opts[0].language,'en-orig')
        self.assertTrue(opts[-1].translated)
        self.assertIn('maschinell übersetzt',opts[-1].label)

    def test_manual_german_before_unknown_english_auto(self):
        opts=t.list_caption_options({'subtitles':{'de':[{'ext':'vtt'}]},'automatic_captions':{'en':[{'ext':'vtt'}]}})
        self.assertEqual(opts[0].kind,'manual')

    def test_render_headers_and_minute_markers(self):
        info=t.VideoInfo('e_4YEmG9KyU','Beispieltitel',(t.CaptionOption('de','auto'),))
        c=[t.Cue(1000,2000,'Hallo'),t.Cue(60500,62000,'Welt')]
        txt=t.render_ai_txt(c,info,info.captions[0])
        for s in ['Titel: Beispieltitel','Sprache: de','[00:00:00]','[00:01:00]','automatische Untertitel','Hallo','Welt']:
            self.assertIn(s,txt)

    def test_local_metadata_without_fake_video_source(self):
        txt=t.render_ai_txt([t.Cue(0,1000,'Hallo')],local_name='demo.vtt')
        self.assertIn('demo.vtt',txt)
        self.assertNotIn('https://',txt)

    def test_retrieve_best_calls_once_and_no_fallback(self):
        info=t.VideoInfo('e_4YEmG9KyU','Test',(t.CaptionOption('en-orig','auto'),t.CaptionOption('de','auto',True)))
        with patch.object(t,'get_video_info',return_value=info), patch.object(t,'fetch_subtitles',return_value=[t.Cue(0,1000,'Hallo')]) as mock:
            x=t.retrieve_best('https://youtu.be/e_4YEmG9KyU')
        self.assertEqual(x[1].language,'en-orig')
        mock.assert_called_once_with(info,info.captions[0])

    def test_no_ytdlp_is_clear_error(self):
        # No installed yt_dlp; offline import should remain possible.
        self.assertEqual(t.parse_subtitles('WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHallo')[0].text,'Hallo')

    def test_paths_limit(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'oversize.vtt'
            with f.open('wb') as out:
                out.seek(8*1024*1024); out.write(b'\0')
            with self.assertRaisesRegex(t.TranscriptError,'groß'):
                t.load_subtitle_file(f)

if __name__=='__main__': unittest.main()
