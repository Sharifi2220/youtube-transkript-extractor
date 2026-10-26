"""Test GUI/process boundary without creating a window or launching an ASR model."""
import json
import subprocess
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from app import ExtractorApp
from local_asr import ASR_MARKER
from transcript_core import TranscriptError


class AsrProcessTests(unittest.TestCase):
    def test_selected_python_interpreter(self):
        payload = {"source_name": "test.wav", "cues": [{"start_ms":0,"end_ms":1,"text":"Hallo"}], "outputs":{"txt":"test.txt"}}
        with patch('app.subprocess.run',return_value=subprocess.CompletedProcess([],0,stdout=ASR_MARKER+json.dumps(payload),stderr='')) as run:
            result=ExtractorApp._run_asr('C:/isoliert/python.exe','C:/test.wav','C:/Ausgaben')
        self.assertEqual(result,payload)
        args,kw=run.call_args
        self.assertEqual(args[0][0],'C:/isoliert/python.exe')
        self.assertEqual(args[0][2:],["--input","C:/test.wav","--output-dir","C:/Ausgaben"])
        self.assertFalse(kw['shell'])
        self.assertEqual(kw['timeout'],10800)

    def test_error_from_worker(self):
        with patch('app.subprocess.run',return_value=subprocess.CompletedProcess([],2,stdout='',stderr='YTX_ASR_ERROR: CUDA fehlt\n')):
            with self.assertRaisesRegex(TranscriptError,'CUDA fehlt'):
                ExtractorApp._run_asr('python','test.wav','out')

    def test_refuse_bad_json(self):
        with patch('app.subprocess.run',return_value=subprocess.CompletedProcess([],0,stdout=ASR_MARKER+'not-json',stderr='')):
            with self.assertRaisesRegex(TranscriptError,'gelesen'):
                ExtractorApp._run_asr('python','test.wav','out')

    def test_oserror_propagated_as_actionable(self):
        with patch('app.subprocess.run',side_effect=FileNotFoundError('python missing')):
            with self.assertRaisesRegex(TranscriptError,'nicht ausgeführt'):
                ExtractorApp._run_asr('C:/notfound/python.exe','test.wav','out')

    def test_no_shell_injection_with_file_name(self):
        malicious='C:/media/A; rm -rf X.wav'
        with patch('app.subprocess.run',return_value=subprocess.CompletedProcess([],2,stdout='',stderr='no whisper')) as run:
            with self.assertRaises(TranscriptError):
                ExtractorApp._run_asr('python',malicious,'out')
        args,kw=run.call_args
        self.assertEqual(args[0][3],malicious)
        self.assertIs(kw['shell'],False)

if __name__=='__main__':unittest.main()
