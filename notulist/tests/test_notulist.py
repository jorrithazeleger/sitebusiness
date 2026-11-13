"""Tests voor Notulist: python3 -m unittest discover tests (vanuit de map notulist)."""
import os
import sys
import tempfile
import textwrap
import time
import unittest
import wave
from unittest import mock

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

import detectie  # noqa: E402
import instellingen  # noqa: E402
import opname  # noqa: E402
import transcriptie  # noqa: E402
from detectie import AudioGebruiker, MeetingDetector, actieve_meeting, herken_app  # noqa: E402
from transcriptie import Segment  # noqa: E402


def lees(pad):
    with open(pad, encoding="utf-8") as fh:
        return fh.read()


def schrijf_wav(pad, samples, rate=16000, kanalen=1):
    data = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(pad, "wb") as w:
        w.setnchannels(kanalen)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(data.tobytes())


class TestHerkennen(unittest.TestCase):
    def test_zoom_op_bundel_en_chrome_helper_op_pad(self):
        self.assertEqual(herken_app(AudioGebruiker(1, bundel="us.zoom.xos")).naam, "Zoom")
        helper = AudioGebruiker(2, pad="/Applications/Google Chrome.app/Contents/Frameworks/"
                                       "Google Chrome Framework.framework/Helpers/Google Chrome Helper.app/x")
        self.assertEqual(herken_app(helper).naam, "Chrome")
        self.assertIsNone(herken_app(AudioGebruiker(3, bundel="com.spotify.client")))

    def test_browsers_uitzetten(self):
        g = AudioGebruiker(2, bundel="com.google.Chrome.helper", invoer=True)
        self.assertEqual(actieve_meeting([g]), "Chrome")
        self.assertIsNone(actieve_meeting([g], browsers=False))

    def test_eigen_proces_telt_niet(self):
        g = AudioGebruiker(99, bundel="us.zoom.xos", invoer=True)
        self.assertIsNone(actieve_meeting([g], eigen_pids={99}))

    def test_alleen_geluid_afspelen_start_geen_meeting(self):
        g = AudioGebruiker(1, bundel="com.microsoft.teams2", uitvoer=True)
        self.assertIsNone(actieve_meeting([g]))
        # maar een lopende Teams-meeting gaat door als je jezelf dempt
        self.assertEqual(actieve_meeting([g], lopend="Teams"), "Teams")

    def test_browser_die_filmpje_afspeelt_houdt_opname_niet_vast(self):
        g = AudioGebruiker(1, bundel="com.google.Chrome", uitvoer=True)
        self.assertIsNone(actieve_meeting([g], lopend="Chrome"))

    def test_lopende_app_gaat_voor(self):
        gs = [AudioGebruiker(1, bundel="com.google.Chrome", invoer=True),
              AudioGebruiker(2, bundel="us.zoom.xos", invoer=True)]
        self.assertEqual(actieve_meeting(gs), "Chrome")
        self.assertEqual(actieve_meeting(gs, lopend="Zoom"), "Zoom")

    def test_fourcc(self):
        self.assertEqual(detectie._fourcc("glob"), 0x676C6F62)


class TestDetector(unittest.TestCase):
    def test_korte_piek_start_niets(self):
        d = MeetingDetector(start_na=4, stop_na=20)
        self.assertIsNone(d.update("Zoom", 0))
        self.assertIsNone(d.update("Zoom", 2))
        self.assertIsNone(d.update(None, 3))
        self.assertIsNone(d.update("Zoom", 5))
        self.assertIsNone(d.update("Zoom", 8))
        self.assertEqual(d.update("Zoom", 9), ("start", "Zoom"))

    def test_stop_pas_na_stilte(self):
        d = MeetingDetector(start_na=0, stop_na=20)
        self.assertEqual(d.update("Teams", 0), ("start", "Teams"))
        self.assertIsNone(d.update(None, 10))
        self.assertIsNone(d.update("Teams", 15))   # even weg, weer terug
        self.assertIsNone(d.update(None, 30))
        self.assertEqual(d.update(None, 36), ("stop", "Teams"))
        self.assertIsNone(d.bezig)

    def test_andere_app_tijdens_wachten_begint_opnieuw(self):
        d = MeetingDetector(start_na=4)
        d.update("Zoom", 0)
        self.assertIsNone(d.update("Chrome", 4))
        self.assertEqual(d.update("Chrome", 8), ("start", "Chrome"))


class TestTekst(unittest.TestCase):
    def test_hallucinaties(self):
        self.assertTrue(transcriptie.is_hallucinatie("Ondertiteld door de Amara.org gemeenschap"))
        self.assertTrue(transcriptie.is_hallucinatie(" Bedankt voor het kijken! "))
        self.assertTrue(transcriptie.is_hallucinatie("..."))
        self.assertFalse(transcriptie.is_hallucinatie("Bedankt voor het kijken naar de offerte, Piet."))
        self.assertFalse(transcriptie.is_hallucinatie("Zullen we om drie uur beginnen?"))

    def test_echo_van_speakers_wordt_verwijderd(self):
        anderen = [Segment(10, 14, "Kun je de cijfers van vorige week delen?")]
        ik = [Segment(10.3, 14.2, "kun je de cijfers van vorige week delen"),
              Segment(15, 17, "Ja, ik stuur ze zo door.")]
        schoon = transcriptie.verwijder_echo(ik, anderen)
        self.assertEqual([s.tekst for s in schoon], ["Ja, ik stuur ze zo door."])

    def test_zelfde_zin_op_ander_moment_blijft(self):
        anderen = [Segment(10, 12, "Akkoord.")]
        ik = [Segment(60, 61, "Akkoord.")]
        self.assertEqual(len(transcriptie.verwijder_echo(ik, anderen)), 1)

    def test_samenvoegen_met_verschuiving(self):
        ik = [Segment(0, 2, "Goedemorgen."), Segment(2.5, 4, "Zullen we beginnen?")]
        anderen = [Segment(4, 6, "Ja, prima.")]
        s = transcriptie.voeg_samen(ik, anderen, verschuiving=1.0)
        self.assertEqual([(x.spreker, x.tekst) for x in s],
                         [("Ik", "Goedemorgen. Zullen we beginnen?"), ("Anderen", "Ja, prima.")])
        self.assertEqual(s[1].start, 5.0)

    def test_tijd_en_datum(self):
        self.assertEqual(transcriptie.tijd(3725.9), "01:02:05")
        ts = time.mktime((2026, 11, 13, 14, 30, 0, 0, 0, -1))
        self.assertEqual(transcriptie.datum_nl(ts), "vrijdag 13 november 2026, 14:30")

    def test_markdown(self):
        ts = time.mktime((2026, 11, 13, 14, 30, 0, 0, 0, -1))
        md = transcriptie.markdown({"app": "Zoom", "start": ts, "einde": ts + 42 * 60},
                                   [Segment(5, 8, "Hallo allemaal.", "Ik")], "large-v3-turbo",
                                   "microfoon en systeemgeluid")
        self.assertIn("# Meeting via Zoom, vrijdag 13 november 2026, 14:30", md)
        self.assertIn("- Duur: 42 minuten", md)
        self.assertIn("**Ik** (00:00:05)  \nHallo allemaal.", md)


class TestAudio(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_omzetten_naar_16khz_mono(self):
        pad = os.path.join(self.tmp, "a.wav")
        t = np.arange(48000) / 48000.0
        stereo = np.stack([np.sin(2 * np.pi * 440 * t)] * 2, axis=1).reshape(-1) * 0.5
        schrijf_wav(pad, stereo, rate=48000, kanalen=2)
        audio = transcriptie.laad_audio(pad)
        self.assertEqual(audio.dtype, np.float32)
        self.assertEqual(len(audio), 16000)
        self.assertAlmostEqual(float(np.max(np.abs(audio))), 0.5, places=2)
        self.assertTrue(transcriptie.heeft_geluid(audio))
        self.assertFalse(transcriptie.heeft_geluid(np.zeros(16000, dtype=np.float32)))

    def test_herstel_na_onverwacht_stoppen(self):
        pad = os.path.join(self.tmp, "mic.wav")
        with wave.open(pad, "wb") as w:  # kop met 0 samples, zoals na een crash
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
        with open(pad, "ab") as fh:
            fh.write(np.full(8000, 1000, dtype="<i2").tobytes())
        transcriptie.herstel_wav(pad)
        with wave.open(pad, "rb") as w:
            self.assertEqual(w.getnframes(), 8000)


class FakeTranscriber:
    model_naam = "test"

    def __init__(self, antwoorden):
        self.antwoorden = antwoorden  # per spoor, op volgorde van aanroep
        self.aanroepen = 0

    def spoor(self, audio, voortgang=None):
        r = self.antwoorden[self.aanroepen]
        self.aanroepen += 1
        if voortgang:
            voortgang(1.0)
        return r


class TestVerwerken(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def maak_meeting(self, mic_stil=False):
        map_ = opname.nieuwe_map(self.tmp, "Zoom", nu=time.mktime((2026, 11, 13, 14, 30, 0, 0, 0, -1)))
        geluid = np.sin(np.arange(32000) / 10.0) * 0.3
        schrijf_wav(os.path.join(map_, opname.MIC), np.zeros(32000) if mic_stil else geluid)
        schrijf_wav(os.path.join(map_, opname.SYSTEEM), geluid)
        opname.schrijf_meta(map_, {"app": "Zoom", "start": 1000.0, "einde": 1600.0,
                                   "mic_start": 1000.0, "systeem_start": 1000.5,
                                   "status": "opgenomen"})
        return map_

    def test_volledige_verwerking(self):
        map_ = self.maak_meeting()
        self.assertTrue(os.path.basename(map_).endswith("-zoom"))
        self.assertEqual(transcriptie.wachtende_mappen(self.tmp), [map_])
        fake = FakeTranscriber([
            [Segment(0.0, 1.5, "Hoi, hoor je me?"), Segment(3.2, 5.0, "Zie je mijn scherm?")],
            [Segment(2.0, 2.8, "Ja, prima."), Segment(2.7, 4.3, "Zie je mijn scherm")],
        ])
        voortgang = []
        uit = transcriptie.verwerk(map_, fake, dict(instellingen.STANDAARD, audio_bewaren=False),
                                   voortgang.append)
        tekst = lees(uit)
        # systeemspoor 0,5 s later begonnen: "Ja, prima." staat op 2,5 s
        self.assertIn("**Anderen** (00:00:02)  \nJa, prima. Zie je mijn scherm", tekst)
        # de echo van "Zie je mijn scherm" in de microfoon is weg
        self.assertEqual(tekst.count("Zie je mijn scherm"), 1)
        self.assertIn("**Ik** (00:00:00)  \nHoi, hoor je me?", tekst)
        self.assertIn("microfoon en systeemgeluid", tekst)
        self.assertFalse(os.path.exists(os.path.join(map_, opname.MIC)))
        self.assertEqual(opname.lees_meta(map_)["status"], "klaar")
        self.assertEqual(transcriptie.wachtende_mappen(self.tmp), [])
        self.assertEqual(voortgang[-1], 1.0)

    def test_stil_spoor_wordt_overgeslagen(self):
        map_ = self.maak_meeting(mic_stil=True)
        fake = FakeTranscriber([[Segment(0, 1, "Alleen de anderen.")]])
        uit = transcriptie.verwerk(map_, fake, dict(instellingen.STANDAARD))
        self.assertEqual(fake.aanroepen, 1)
        tekst = lees(uit)
        self.assertIn("Opgenomen: systeemgeluid", tekst)
        self.assertTrue(os.path.exists(os.path.join(map_, opname.MIC)))  # audio bewaard


class TestInstellingen(unittest.TestCase):
    def test_laden_en_bewaren(self):
        pad = os.path.join(tempfile.mkdtemp(), "sub", "instellingen.json")
        self.assertEqual(instellingen.laad(pad), instellingen.STANDAARD)
        data = instellingen.laad(pad)
        data["model"] = "small"
        instellingen.bewaar(data, pad)
        with open(pad, "a", encoding="utf-8") as fh:
            fh.write("")
        self.assertEqual(instellingen.laad(pad)["model"], "small")
        with open(pad, "w", encoding="utf-8") as fh:
            fh.write("{kapot")
        self.assertEqual(instellingen.laad(pad), instellingen.STANDAARD)

    def test_unieke_mappen(self):
        tmp = tempfile.mkdtemp()
        a = opname.nieuwe_map(tmp, "Google Chrome", nu=0)
        b = opname.nieuwe_map(tmp, "Google Chrome", nu=0)
        self.assertTrue(a.endswith("-google-chrome"))
        self.assertTrue(b.endswith("-google-chrome-2"))


class TestSysteemOpname(unittest.TestCase):
    def nep_helper(self, inhoud):
        pad = os.path.join(tempfile.mkdtemp(), "helper")
        with open(pad, "w") as fh:
            fh.write("#!%s\n%s" % (sys.executable, textwrap.dedent(inhoud)))
        os.chmod(pad, 0o755)
        return pad

    def test_start_en_stop(self):
        helper = self.nep_helper("""
            import signal, sys, time
            def stop(*_):
                open(sys.argv[1], "w").write("klaar")
                sys.exit(0)
            signal.signal(signal.SIGINT, stop)
            print("READY 1234.5", flush=True)
            while True:
                time.sleep(0.1)
        """)
        uit = os.path.join(tempfile.mkdtemp(), "systeem.wav")
        s = opname.SysteemOpname(helper, uit)
        s.start()
        self.assertEqual(s.start_tijd, 1234.5)
        self.assertTrue(s.actief())
        s.stop()
        self.assertEqual(lees(uit), "klaar")

    def test_geen_toestemming_geeft_duidelijke_fout(self):
        helper = self.nep_helper("""
            import sys
            print("starten mislukt: geen toestemming", file=sys.stderr, flush=True)
            sys.exit(2)
        """)
        s = opname.SysteemOpname(helper, os.path.join(tempfile.mkdtemp(), "x.wav"))
        with self.assertRaises(RuntimeError) as ctx:
            s.start(wacht=5)
        time.sleep(0.2)
        self.assertIn("starten mislukt", str(ctx.exception) + " ".join(s._stderr))


class NepOpname:
    gestart = []

    def __init__(self, basis, app, automatisch=True):
        self.app, self.automatisch, self.map = app, automatisch, os.path.join(basis, app)
        self.systeem = None
        self.waarschuwing = None
        self.begin = time.time()

    def start(self):
        NepOpname.gestart.append(self.app)

    def duur(self):
        return time.time() - self.begin

    def stop(self):
        return self.map


class NepAudio:
    def __init__(self):
        self.nu = []

    def gebruikers(self):
        return self.nu


class TestKern(unittest.TestCase):
    def setUp(self):
        import notulist
        self.notulist = notulist
        NepOpname.gestart = []
        self.config = dict(instellingen.STANDAARD, map=tempfile.mkdtemp(),
                           start_na_seconden=4, stop_na_seconden=10)
        self.audio = NepAudio()
        p = mock.patch.object(notulist, "Opname", NepOpname)
        p.start()
        self.addCleanup(p.stop)
        self.meldingen = []
        self.kern = notulist.Kern(self.config, self.audio, lambda t, m: self.meldingen.append(t))
        self.kern.plan_transcriptie = lambda map_: self.meldingen.append("plan " + map_)

    def wacht(self):
        self.kern._acties.submit(lambda: None).result(5)

    def test_meeting_start_en_stopt_vanzelf(self):
        self.audio.nu = [AudioGebruiker(1, bundel="us.zoom.xos", invoer=True)]
        self.kern.tik(0)
        self.kern.tik(4)
        self.wacht()
        self.assertEqual(NepOpname.gestart, ["Zoom"])
        self.assertIsNotNone(self.kern.opname)
        self.audio.nu = []
        self.kern.tik(6)
        self.assertIsNotNone(self.kern.opname)
        self.kern.tik(16)
        self.wacht()
        self.assertIsNone(self.kern.opname)
        self.assertIn("Opname gestart", self.meldingen)
        self.assertTrue(any(m.startswith("plan ") for m in self.meldingen))

    def test_handmatig_gestopt_start_niet_meteen_opnieuw(self):
        self.audio.nu = [AudioGebruiker(1, bundel="us.zoom.xos", invoer=True)]
        self.kern.tik(0)
        self.kern.tik(4)
        self.wacht()
        self.kern.stop(handmatig=True)
        self.wacht()
        for t in range(6, 40, 2):
            self.kern.tik(t)
        self.wacht()
        self.assertEqual(NepOpname.gestart, ["Zoom"])
        # na de meeting weer alles normaal
        self.audio.nu = []
        self.kern.tik(42)
        self.audio.nu = [AudioGebruiker(1, bundel="com.microsoft.teams2", invoer=True)]
        self.kern.tik(50)
        self.kern.tik(54)
        self.wacht()
        self.assertEqual(NepOpname.gestart, ["Zoom", "Teams"])

    def test_handmatige_opname_stopt_niet_vanzelf(self):
        self.kern.start("handmatig", automatisch=False)
        self.wacht()
        for t in range(0, 60, 2):
            self.kern.tik(t)
        self.assertIsNotNone(self.kern.opname)

    def test_automatisch_uit(self):
        self.config["automatisch_opnemen"] = False
        self.audio.nu = [AudioGebruiker(1, bundel="us.zoom.xos", invoer=True)]
        for t in range(0, 20, 2):
            self.kern.tik(t)
        self.wacht()
        self.assertEqual(NepOpname.gestart, [])


if __name__ == "__main__":
    unittest.main()
