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

    def test_alleen_geluid_afspelen_is_geen_meeting(self):
        # Teams houdt de speakers ook na de meeting open; dat mag een opname niet vasthouden
        g = AudioGebruiker(1, bundel="com.microsoft.teams2", uitvoer=True)
        self.assertIsNone(actieve_meeting([g]))
        self.assertIsNone(actieve_meeting([g], lopend="Teams"))

    def test_beschrijving_voor_logboek(self):
        gs = [AudioGebruiker(1, bundel="us.zoom.xos", invoer=True),
              AudioGebruiker(2, bundel="com.spotify.client", uitvoer=True),
              AudioGebruiker(3, pad="/Applications/Iets.app/Contents/MacOS/Iets", invoer=True),
              AudioGebruiker(4, bundel="us.zoom.xos", invoer=True)]
        self.assertEqual(detectie.beschrijf(gs, eigen_pids={4}), ["Iets", "Zoom"])

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
        self.stil = 0.0

    def start(self):
        NepOpname.gestart.append(self.app)

    def duur(self):
        return time.time() - self.begin

    def stil_sinds(self):
        return self.stil

    def niveaus(self):
        return {"ik": 0.1, "anderen": None}

    def stop(self):
        return self.map


class NepAudio:
    def __init__(self):
        self.nu = []

    def gebruikers(self):
        return self.nu


class TestKern(unittest.TestCase):
    def setUp(self):
        import kern
        NepOpname.gestart = []
        self.config = dict(instellingen.STANDAARD, map=tempfile.mkdtemp(),
                           start_na_seconden=4, stop_na_seconden=10)
        self.audio = NepAudio()
        p = mock.patch.object(kern, "Opname", NepOpname)
        p.start()
        self.addCleanup(p.stop)
        self.meldingen = []
        self.kern = kern.Kern(self.config, self.audio, lambda t, m: self.meldingen.append(t))
        self.kern.plan = lambda map_, soort="uitschrijven": self.meldingen.append("plan " + map_)

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

    def test_stilte_stopt_een_opname_die_niet_vanzelf_stopt(self):
        # Chrome houdt de microfoon na de meeting vast, maar het is al lang stil
        self.audio.nu = [AudioGebruiker(1, bundel="com.google.Chrome.helper", invoer=True)]
        self.kern.tik(0)
        self.kern.tik(4)
        self.wacht()
        self.kern.opname.stil = 5 * 60 + 1
        self.kern.tik(6)
        self.wacht()
        self.assertIsNone(self.kern.opname)
        self.assertIn("Opname gestopt", self.meldingen)
        # zolang Chrome de microfoon vasthoudt niet opnieuw beginnen
        for t in range(8, 40, 2):
            self.kern.tik(t)
        self.wacht()
        self.assertEqual(NepOpname.gestart, ["Chrome"])

    def test_handmatige_opname_stopt_niet_bij_stilte(self):
        self.kern.start("handmatig", automatisch=False)
        self.wacht()
        self.kern.opname.stil = 3600
        self.kern.tik(0)
        self.assertIsNotNone(self.kern.opname)

    def test_logt_wie_de_microfoon_gebruikt(self):
        self.audio.nu = [AudioGebruiker(1, bundel="us.zoom.xos", invoer=True)]
        self.kern.tik(0)
        self.assertEqual(self.kern.gezien, ["Zoom"])
        self.assertEqual(self.kern.status()["gezien"], ["Zoom"])


class TestSysteemNiveau(unittest.TestCase):
    def test_level_regels_houden_geluid_bij(self):
        s = opname.SysteemOpname("x", "y")
        s.verwerk_regel("LEVEL 0.0001\n")
        self.assertIsNone(s.laatste_geluid)
        s.verwerk_regel("LEVEL 0.2500\n")
        self.assertAlmostEqual(s.niveau, 0.25)
        self.assertIsNotNone(s.laatste_geluid)
        s.verwerk_regel("onzin")


def maak_meeting(basis, naam, app="Zoom", titel=None, segmenten=None, samenvatting=None, start=None):
    import json
    m = os.path.join(basis, naam)
    os.makedirs(m)
    meta = {"app": app, "start": start or 1794576600.0, "einde": (start or 1794576600.0) + 1800,
            "status": "klaar"}
    if titel:
        meta["titel"] = titel
    opname.schrijf_meta(m, meta)
    if segmenten is not None:
        with open(os.path.join(m, transcriptie.TRANSCRIPT), "w") as fh:
            fh.write("# x\n")
        with open(os.path.join(m, transcriptie.TRANSCRIPT_JSON), "w") as fh:
            json.dump({"model": "test", "sporen": "microfoon", "segmenten": segmenten}, fh)
    if samenvatting is not None:
        with open(os.path.join(m, "samenvatting.json"), "w") as fh:
            json.dump(samenvatting, fh)
    return m


SEGS = [{"start": 1.0, "einde": 3.0, "spreker": "Ik", "tekst": "Zullen we het budget bespreken?"},
        {"start": 4.0, "einde": 8.0, "spreker": "Anderen", "tekst": "Ja, de offerte voor Impazz is binnen."}]
SAMENVATTING = {"titel": "Budget en offerte", "samenvatting": "Het budget is besproken.",
                "punten": ["Offerte is binnen"], "besluiten": [], "open_vragen": ["Wanneer tekenen?"],
                "actiepunten": [{"wat": "Offerte nalopen", "wie": "Ik", "wanneer": "vrijdag"}]}


class TestMeetings(unittest.TestCase):
    def setUp(self):
        import meetings
        self.m = meetings
        self.basis = tempfile.mkdtemp()
        maak_meeting(self.basis, "20261113-1000-zoom", segmenten=SEGS, samenvatting=SAMENVATTING, start=2000)
        maak_meeting(self.basis, "20261112-0900-teams", app="Teams", titel="Weekstart", start=1000)

    def test_lijst_nieuwste_eerst_met_titels(self):
        lijst = self.m.lijst(self.basis)
        self.assertEqual([i["id"] for i in lijst], ["20261113-1000-zoom", "20261112-0900-teams"])
        self.assertEqual(lijst[0]["titel"], "Meeting via Zoom")
        self.assertEqual(lijst[1]["titel"], "Weekstart")
        self.assertTrue(lijst[0]["samenvatting"])

    def test_zoeken_in_transcript_en_samenvatting(self):
        self.assertEqual([i["id"] for i in self.m.zoek(self.basis, "impazz offerte")], ["20261113-1000-zoom"])
        self.assertIn("Impazz", self.m.zoek(self.basis, "impazz")[0]["fragment"])
        self.assertEqual([i["id"] for i in self.m.zoek(self.basis, "weekstart")], ["20261112-0900-teams"])
        self.assertEqual(self.m.zoek(self.basis, "nalopen")[0]["id"], "20261113-1000-zoom")
        self.assertEqual(self.m.zoek(self.basis, "bestaatniet"), [])

    def test_ongeldige_id_wordt_geweigerd(self):
        self.assertIsNone(self.m.pad_van(self.basis, "../etc"))
        self.assertIsNone(self.m.detail(self.basis, "bestaat-niet"))

    def test_wijzigen_en_tekst(self):
        self.assertTrue(self.m.wijzig(self.basis, "20261113-1000-zoom", titel="  Gesprek   met Impazz ", gedaan=[0, 0, -1]))
        d = self.m.detail(self.basis, "20261113-1000-zoom")
        self.assertEqual(d["titel"], "Gesprek met Impazz")
        self.assertEqual(d["gedaan"], [0])
        tekst = self.m.als_tekst(self.basis, "20261113-1000-zoom")
        self.assertIn("Actiepunten:\n- Offerte nalopen (Ik, vrijdag)", tekst)
        self.assertIn("Anderen (00:00:04): Ja, de offerte", tekst)
        self.assertTrue(self.m.exportnaam(self.basis, "20261113-1000-zoom").endswith("-notulen-gesprek-met-impazz.txt"))
        self.m.wijzig(self.basis, "20261113-1000-zoom", titel="")
        self.assertEqual(self.m.detail(self.basis, "20261113-1000-zoom")["titel"], "Meeting via Zoom")

    def test_naar_prullenmand(self):
        prul = tempfile.mkdtemp()
        self.assertTrue(self.m.naar_prullenmand(self.basis, "20261112-0900-teams", prul))
        self.assertEqual(os.listdir(prul), ["Notulist 20261112-0900-teams"])
        self.assertEqual(len(self.m.lijst(self.basis)), 1)


class NepClaude:
    """Doet zich voor als anthropic.Anthropic() en onthoudt het verzoek."""

    def __init__(self, antwoord, stop="end_turn"):
        import types
        self.verzoek = None
        blok = types.SimpleNamespace(type="text", text=antwoord)
        resultaat = types.SimpleNamespace(stop_reason=stop, content=[blok], _request_id="req_test")

        def create(**kwargs):
            self.verzoek = kwargs
            return resultaat

        self.beta = types.SimpleNamespace(messages=types.SimpleNamespace(create=create))


class TestSamenvatting(unittest.TestCase):
    def setUp(self):
        import samenvatting
        self.s = samenvatting
        self.basis = tempfile.mkdtemp()
        self.map = maak_meeting(self.basis, "20261113-1000-zoom", segmenten=SEGS)

    def test_maakt_notulen_en_bewaart_ze(self):
        import json
        nep = NepClaude(json.dumps(SAMENVATTING))
        data = self.s.maak(self.map, dict(instellingen.STANDAARD, naam_ik="Jorrit"), client=nep)
        self.assertEqual(data["titel"], "Budget en offerte")
        v = nep.verzoek
        self.assertEqual(v["model"], "claude-opus-5-5")
        self.assertEqual(v["fallbacks"], "default")
        self.assertEqual(v["output_config"]["format"]["type"], "json_schema")
        self.assertIn('"Jorrit" is degene', v["system"])
        self.assertIn("[00:00:04] Anderen: Ja, de offerte voor Impazz is binnen.", v["messages"][0]["content"])
        self.assertEqual(opname.lees_meta(self.map)["ai_titel"], "Budget en offerte")
        with open(os.path.join(self.map, "samenvatting.md"), encoding="utf-8") as fh:
            md = fh.read()
        self.assertIn("- [ ] Offerte nalopen (Ik, vrijdag)", md)

    def test_weigering_en_onzin(self):
        with self.assertRaises(self.s.SamenvattingFout):
            self.s.maak(self.map, instellingen.STANDAARD, client=NepClaude("", stop="refusal"))
        with self.assertRaises(self.s.SamenvattingFout):
            self.s.maak(self.map, instellingen.STANDAARD, client=NepClaude("geen json"))

    def test_zonder_transcript(self):
        leeg = maak_meeting(self.basis, "leeg")
        with self.assertRaises(self.s.SamenvattingFout):
            self.s.maak(leeg, instellingen.STANDAARD, client=NepClaude("{}"))

    def test_schema_is_streng(self):
        def check(schema):
            if schema.get("type") == "object":
                self.assertFalse(schema["additionalProperties"])
                self.assertEqual(set(schema["required"]), set(schema["properties"]))
                for sub in schema["properties"].values():
                    check(sub)
            if schema.get("type") == "array":
                check(schema["items"])
        check(self.s.SCHEMA)


class TestAfspeelbestand(unittest.TestCase):
    def test_mix_van_beide_sporen(self):
        m = tempfile.mkdtemp()
        schrijf_wav(os.path.join(m, opname.MIC), np.full(16000, 0.2))
        schrijf_wav(os.path.join(m, opname.SYSTEEM), np.full(16000, 0.3))
        with mock.patch("shutil.which", return_value=None):
            pad = transcriptie.maak_afspeelbestand(m, verschuiving=0.5)
        self.assertTrue(pad.endswith(transcriptie.AFSPEEL_WAV))
        audio = transcriptie.laad_audio(pad)
        self.assertEqual(len(audio), 24000)               # 1 s + 0,5 s verschoven
        self.assertAlmostEqual(float(audio[4000]), 0.2, places=2)   # alleen ik
        self.assertAlmostEqual(float(audio[12000]), 0.5, places=2)  # samen
        self.assertAlmostEqual(float(audio[20000]), 0.3, places=2)  # alleen de anderen


class TestServer(unittest.TestCase):
    def setUp(self):
        import json
        import urllib.request
        import kern
        import server
        self.json, self.urllib = json, urllib.request
        self.basis = tempfile.mkdtemp()
        maak_meeting(self.basis, "20261113-1000-zoom", segmenten=SEGS, samenvatting=SAMENVATTING)
        self.wav = os.path.join(self.basis, "20261113-1000-zoom", transcriptie.AFSPEEL_WAV)
        schrijf_wav(self.wav, np.zeros(1000))
        p = mock.patch.object(instellingen, "BESTAND", os.path.join(self.basis, "instellingen.json"))
        p.start()
        self.addCleanup(p.stop)
        self.config = dict(instellingen.STANDAARD, map=self.basis)
        self.kern = kern.Kern(self.config, None)
        self.kern.plan = lambda map_, soort="uitschrijven": setattr(self, "gepland", (os.path.basename(map_), soort))
        self.prul = tempfile.mkdtemp()
        self.srv = server.Server(self.kern, {"prullenmand": self.prul, "toestemmingen": lambda: "alles goed"})
        self.srv.start()
        self.addCleanup(self.srv.stop)
        self.basis_url = "http://127.0.0.1:%d" % self.srv.poort

    def vraag(self, methode, pad, body=None, token=True, headers=None):
        import urllib.error
        h = {"Content-Type": "application/json"}
        if token:
            h["X-Notulist-Token"] = self.srv.token
        h.update(headers or {})
        data = self.json.dumps(body).encode() if body is not None else None
        req = self.urllib.Request(self.basis_url + pad, data=data, headers=h, method=methode)
        try:
            with self.urllib.urlopen(req, timeout=5) as r:
                return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)

    def test_zonder_sleutel_geen_toegang(self):
        self.assertEqual(self.vraag("GET", "/api/status", token=False)[0], 403)
        self.assertEqual(self.vraag("GET", "/", token=False)[0], 403)
        self.assertEqual(self.vraag("GET", "/api/status", headers={"Host": "evil.example"})[0], 403)
        self.assertEqual(self.vraag("GET", "/?t=" + self.srv.token, token=False)[0], 200)
        self.assertEqual(self.vraag("GET", "/web/app.js", token=False)[0], 200)

    def test_meetings_en_wijzigen(self):
        status, body, _ = self.vraag("GET", "/api/meetings")
        self.assertEqual(self.json.loads(body)[0]["id"], "20261113-1000-zoom")
        status, body, _ = self.vraag("GET", "/api/meetings?q=impazz")
        self.assertEqual(len(self.json.loads(body)), 1)
        status, body, _ = self.vraag("PATCH", "/api/meetings/20261113-1000-zoom", {"titel": "Nieuw", "gedaan": [0]})
        d = self.json.loads(body)
        self.assertEqual((d["titel"], d["gedaan"], d["audio"]), ("Nieuw", [0], True))
        self.assertEqual(self.vraag("PATCH", "/api/meetings/20261113-1000-zoom", {"gedaan": "x"})[0], 400)
        self.assertEqual(self.vraag("GET", "/api/meetings/bestaat-niet")[0], 404)

    def test_audio_met_bereik(self):
        status, body, headers = self.vraag("GET", "/api/meetings/20261113-1000-zoom/audio", headers={"Range": "bytes=10-19"})
        self.assertEqual(status, 206)
        self.assertEqual(len(body), 10)
        self.assertEqual(headers["Content-Range"], "bytes 10-19/%d" % os.path.getsize(self.wav))

    def test_acties(self):
        self.assertEqual(self.vraag("POST", "/api/meetings/20261113-1000-zoom/uitschrijven")[0], 200)
        self.assertEqual(self.gepland, ("20261113-1000-zoom", "uitschrijven"))
        with mock.patch("samenvatting.beschikbaar", return_value=False):
            self.assertEqual(self.vraag("POST", "/api/meetings/20261113-1000-zoom/samenvatten")[0], 400)
        status, body, _ = self.vraag("POST", "/api/toestemmingen")
        self.assertEqual(self.json.loads(body)["tekst"], "alles goed")
        self.assertEqual(self.vraag("DELETE", "/api/meetings/20261113-1000-zoom")[0], 200)
        self.assertEqual(len(os.listdir(self.prul)), 1)

    def test_instellingen(self):
        status, body, _ = self.vraag("PATCH", "/api/instellingen", {"stop_na_seconden": 30, "onbekend": 1})
        self.assertEqual(status, 200)
        self.assertEqual(self.kern.detector.stop_na, 30)
        self.assertEqual(instellingen.laad(instellingen.BESTAND)["stop_na_seconden"], 30)
        self.assertEqual(self.vraag("PATCH", "/api/instellingen", {"stop_na_seconden": "veel"})[0], 400)
        self.assertEqual(self.vraag("PATCH", "/api/instellingen", {"model": "groot"})[0], 400)
        self.assertEqual(self.vraag("PATCH", "/api/instellingen", {"automatisch_opnemen": 1})[0], 400)


if __name__ == "__main__":
    unittest.main()
