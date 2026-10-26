"""ASR adaptation regression tests: completely synthetic; no Whisper/CUDA/media network."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import local_asr as a
from transcript_core import Cue, parse_subtitles


class FakeWhisper:
    def __init__(self, segments=None, language="de"):
        self.segments = segments if segments is not None else [
            {"start": 0.0, "end": 1.3, "text": "Guten Morgen"},
            {"start": 65.0, "end": 66.1, "text": "Hallo سلام"},
        ]
        self.language = language
        self.calls = []

    def transcribe(self, filename, **kwargs):
        self.calls.append((filename, kwargs))
        return {"segments": self.segments, "language": self.language, "text": "test"}


class AsrTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "Tonspur ä.mp3"
        self.source.write_bytes(b"ONLY_FAKE_AUDIO_BYTES_NO_REAL_MEDIA")

    def run_fake(self, **kwargs):
        engine = FakeWhisper(**kwargs)
        result = a.transcribe_one(self.source, model_loader=lambda: engine)
        return result, engine

    def test_single_explicit_file_allowed(self):
        self.assertEqual(a.verify_source(self.source), self.source.resolve())

    def test_directory_blocked(self):
        with self.assertRaises(a.AsrError): a.verify_source(self.root)

    def test_url_and_invalid_extension_blocked(self):
        with self.assertRaises(a.AsrError): a.verify_source("https://www.youtube.com/watch?v=PCXsBHeLh-w")
        f=self.root/'evil.txt';f.write_bytes(b'x')
        with self.assertRaises(a.AsrError):a.verify_source(f)

    def test_empty_file_blocked(self):
        f=self.root/'empty.wav';f.touch()
        with self.assertRaises(a.AsrError):a.verify_source(f)

    def test_symlink_blocked(self):
        link=self.root/'alias.wav'
        try:link.symlink_to(self.source)
        except (OSError, NotImplementedError):self.skipTest('No symlink permissions')
        with self.assertRaises(a.AsrError):a.verify_source(link)

    def test_fake_cpu_single_file_no_network(self):
        result, engine = self.run_fake()
        self.assertEqual(result.device,'cpu')
        self.assertEqual(len(result.cues),2)
        self.assertIn('Guten',result.cues[0].text)
        self.assertEqual(engine.calls[0][1]['fp16'],False)
        self.assertTrue(result.sha256)
        self.assertEqual(result.source_name,self.source.name)

    def test_cuda_explicit_injection(self):
        engine=FakeWhisper()
        result=a.transcribe_one(self.source,model_loader=lambda:engine,requested_device='cuda')
        self.assertEqual(result.device,'cuda')
        self.assertTrue(engine.calls[0][1]['fp16'])

    def test_source_hash_unchanged(self):
        orig=hashlib.sha256(self.source.read_bytes()).hexdigest()
        result,_=self.run_fake()
        self.assertEqual(result.sha256,orig)
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(),orig)

    def test_source_mutation_rejected(self):
        source=self.source
        class Mutator(FakeWhisper):
            def transcribe(self,*args,**kwargs):
                source.write_bytes(b'ALTERED')
                return super().transcribe(*args,**kwargs)
        with self.assertRaisesRegex(a.AsrError,'INPUT_CHANGED'):
            a.transcribe_one(source,model_loader=lambda:Mutator())

    def test_no_speech_rejected(self):
        with self.assertRaisesRegex(a.AsrError,'NO_SPEECH'):
            self.run_fake(segments=[{'start':0,'end':2,'text':'   '}])

    def test_no_timestamp_rejected(self):
        with self.assertRaisesRegex(a.AsrError,'Zeitmarken'):
            self.run_fake(segments=[{'text':'hello'}])

    def test_invalid_times_rejected(self):
        with self.assertRaisesRegex(a.AsrError,'Zeitmarke'):
            self.run_fake(segments=[{'start':4,'end':3,'text':'hello'}])

    def test_zero_duration_kept_as_1ms(self):
        r,_=self.run_fake(segments=[{'start':2,'end':2,'text':'Hallo'}])
        self.assertEqual(r.cues, (Cue(2000,2001,'Hallo'),))

    def test_txt_provenance(self):
        r,_=self.run_fake()
        text=a.ai_text(r)
        for needle in ('LOKALE WHISPER',self.source.name, 'Whisper base',r.sha256,'[00:00:00]','[00:01:00]', 'سلام'):
            self.assertIn(needle,text)

    def test_export_all_formats_and_roundtrip(self):
        r,_=self.run_fake()
        out=a.save_asr(r,self.root/'TRANSKRIPTE_TESTAUSGABEN')
        self.assertEqual(set(out),{'txt','srt','vtt','json'})
        self.assertEqual(parse_subtitles(Path(out['srt']).read_text(encoding='utf-8')), list(r.cues))
        self.assertEqual(parse_subtitles(Path(out['vtt']).read_text(encoding='utf-8')), list(r.cues))
        self.assertEqual(json.loads(Path(out['json']).read_text(encoding='utf-8'))['source_sha256'],r.sha256)
        self.assertTrue(Path(out['txt']).read_bytes().startswith(b'\xef\xbb\xbf'))
        self.assertIn('.asr.', Path(out['txt']).name)

    def test_no_overwrite_any_export(self):
        r,_=self.run_fake()
        folder=self.root/'out';first=a.save_asr(r,folder)
        snap={kind:Path(p).read_bytes() for kind,p in first.items()}
        with self.assertRaisesRegex(a.AsrError,'existiert'):
            a.save_asr(r,folder)
        self.assertEqual(snap,{kind:Path(p).read_bytes() for kind,p in first.items()})

    def test_failed_write_rollback(self):
        r,_=self.run_fake()
        orig=Path.open
        count={'n':0}
        def fail_second(path, mode='r', *args, **kwargs):
            if mode == 'x':
                count['n']+=1
                if count['n']==2: raise OSError('simulated disk error')
            return orig(path,mode,*args,**kwargs)
        with patch.object(Path,'open',autospec=False,side_effect=fail_second):
            with self.assertRaisesRegex(a.AsrError,'Ausgabe'):
                a.save_asr(r,self.root/'out')
        self.assertEqual(list((self.root/'out').iterdir()),[])

    def test_output_folder_project_relative(self):
        unpacked=self.root/'Unpacked';unpacked.mkdir()
        self.assertEqual(a.output_folder(unpacked),unpacked.resolve()/'TRANSKRIPTE_TESTAUSGABEN')
        nested=self.root/'workspace'/'Unpacked';nested.mkdir(parents=True)
        self.assertEqual(a.output_folder(nested),nested.resolve()/'TRANSKRIPTE_TESTAUSGABEN')

    def test_payload_serializable_and_exact(self):
        r,_=self.run_fake()
        data=json.loads(json.dumps(a.result_payload(r,{'txt':'test.txt'}),ensure_ascii=False))
        self.assertEqual([t['text'] for t in data['cues']],['Guten Morgen','Hallo سلام'])
        self.assertEqual(data['outputs']['txt'],'test.txt')

    def test_wrong_device_rejected(self):
        with self.assertRaises(a.AsrError):
            a.transcribe_one(self.source,requested_device='gpu',model_loader=FakeWhisper)

    def test_cached_model_required_before_import(self):
        with patch.object(Path,'home',return_value=self.root):
            with self.assertRaisesRegex(a.AsrError,'nicht lokal vorhanden'):
                a.transcribe_one(self.source)


    def test_cached_model_is_loaded_by_path_no_download(self):
        fake_home=self.root
        cached=fake_home/'.cache'/'whisper'/'base.pt'
        cached.parent.mkdir(parents=True)
        cached.write_bytes(b'fake cached model used only with mocked loader')
        engine=FakeWhisper()
        class FakeTorch:
            class cuda:
                @staticmethod
                def is_available():return True
        class FakeWhisperModule:
            def load_model(self,name,device):
                self.model_path=name;self.device=device
                return engine
        whisper_module=FakeWhisperModule()
        def importer(name):
            return {'torch':FakeTorch(),'whisper':whisper_module}[name]
        with patch.object(Path,'home',return_value=fake_home), patch.object(a.importlib,'import_module',side_effect=importer):
            result=a.transcribe_one(self.source)
        self.assertEqual(result.device,'cuda')
        self.assertEqual(whisper_module.model_path,str(cached))
        self.assertEqual(whisper_module.device,'cuda')
        self.assertTrue(engine.calls[0][1]['fp16'])

    def test_error_message_without_whisper_runtime(self):
        with patch.object(a,'transcribe_one',side_effect=a.AsrError('TEST_ERROR')):
            self.assertEqual(a.main(['--input',str(self.source),'--output-dir',str(self.root/'out')]),2)
        self.assertFalse((self.root/'out').exists())

if __name__=='__main__': unittest.main()
