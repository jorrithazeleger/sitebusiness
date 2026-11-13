// notulist-audiocap: neemt het systeemgeluid op (alles wat de Mac afspeelt, dus ook de andere
// deelnemers van een meeting) via ScreenCaptureKit, en schrijft het als WAV (16 kHz, mono, 16-bit).
//
// Gebruik:
//   notulist-audiocap <uitvoer.wav>   opnemen tot SIGINT of SIGTERM; meldt "READY <unix-tijd>"
//                                     op stdout zodra de opname loopt (tijd = begin van het bestand)
//   notulist-audiocap --check         controleert de toestemming voor schermopname
//                                     (exit 0 = in orde, 2 = geen toestemming)
//
// Bouwen: swiftc -O -swift-version 5 -target arm64-apple-macos13.0 -o notulist-audiocap audiocap.swift

import AVFoundation
import CoreMedia
import Foundation
import ScreenCaptureKit

let sampleRate = 16000.0

func meld(_ tekst: String) {
    print(tekst)
    fflush(stdout)
}

func fout(_ tekst: String) {
    FileHandle.standardError.write((tekst + "\n").data(using: .utf8)!)
}

final class Recorder: NSObject, SCStreamOutput, SCStreamDelegate {
    let url: URL
    let queue = DispatchQueue(label: "nl.notulist.audiocap")
    let doelFormaat = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: sampleRate,
                                    channels: 1, interleaved: false)!
    var stream: SCStream?
    var file: AVAudioFile?
    var converter: AVAudioConverter?
    var converterBron: AVAudioFormat?
    var startTijd = CMTime.invalid
    var geschreven: AVAudioFramePosition = 0

    init(url: URL) {
        self.url = url
    }

    func start() async throws {
        let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
        guard let display = content.displays.first else {
            throw NSError(domain: "notulist", code: 1,
                          userInfo: [NSLocalizedDescriptionKey: "geen beeldscherm gevonden"])
        }
        let filter = SCContentFilter(display: display, excludingApplications: [], exceptingWindows: [])
        let config = SCStreamConfiguration()
        config.capturesAudio = true
        config.excludesCurrentProcessAudio = true
        config.sampleRate = Int(sampleRate)
        config.channelCount = 1
        // Beeld is niet nodig: zo klein en traag mogelijk.
        config.width = 2
        config.height = 2
        config.minimumFrameInterval = CMTime(value: 1, timescale: 1)
        config.showsCursor = false

        let instellingen: [String: Any] = [
            AVFormatIDKey: kAudioFormatLinearPCM,
            AVSampleRateKey: sampleRate,
            AVNumberOfChannelsKey: 1,
            AVLinearPCMBitDepthKey: 16,
            AVLinearPCMIsFloatKey: false,
            AVLinearPCMIsBigEndianKey: false,
        ]
        file = try AVAudioFile(forWriting: url, settings: instellingen,
                               commonFormat: .pcmFormatFloat32, interleaved: false)

        let stream = SCStream(filter: filter, configuration: config, delegate: self)
        try stream.addStreamOutput(self, type: .audio, sampleHandlerQueue: queue)
        try stream.addStreamOutput(self, type: .screen, sampleHandlerQueue: queue)
        self.stream = stream

        // Het begin van het bestand: tot het eerste geluid wordt stilte geschreven, zodat de
        // tijd in het bestand gelijk loopt met de klok.
        let unix = Date().timeIntervalSince1970
        queue.sync { startTijd = CMClockGetTime(CMClockGetHostTimeClock()) }
        try await stream.startCapture()
        meld(String(format: "READY %.3f", unix))
    }

    func stop() async {
        if let stream = stream {
            try? await stream.stopCapture()
        }
        queue.sync {
            file = nil  // sluit het bestand en schrijft de WAV-kop
        }
    }

    // MARK: SCStreamOutput

    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer,
                of type: SCStreamOutputType) {
        guard type == .audio, CMSampleBufferIsValid(sampleBuffer), let file = file else { return }
        guard let buffer = pcm(sampleBuffer) else { return }

        let pts = CMSampleBufferGetPresentationTimeStamp(sampleBuffer)
        if startTijd.isValid && pts.isValid {
            let sinds = CMTimeGetSeconds(CMTimeSubtract(pts, startTijd))
            let verwacht = AVAudioFramePosition(sinds * sampleRate)
            let gat = verwacht - geschreven
            // Gaten groter dan 50 ms (bijvoorbeeld omdat er even niets klonk) opvullen met stilte.
            if gat > AVAudioFramePosition(sampleRate * 0.05) && gat < AVAudioFramePosition(sampleRate * 3600 * 8) {
                schrijfStilte(gat, naar: file)
            }
        }
        do {
            try file.write(from: buffer)
            geschreven += AVAudioFramePosition(buffer.frameLength)
        } catch {
            fout("schrijven mislukt: \(error.localizedDescription)")
        }
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        fout("opname gestopt: \(error.localizedDescription)")
        queue.async {
            self.file = nil
            exit(1)
        }
    }

    // MARK: hulpjes

    func schrijfStilte(_ frames: AVAudioFramePosition, naar file: AVAudioFile) {
        var rest = frames
        while rest > 0 {
            let n = AVAudioFrameCount(min(rest, AVAudioFramePosition(sampleRate)))
            guard let stil = AVAudioPCMBuffer(pcmFormat: doelFormaat, frameCapacity: n),
                  let kanaal = stil.floatChannelData else { return }
            stil.frameLength = n
            kanaal[0].initialize(repeating: 0, count: Int(n))
            do {
                try file.write(from: stil)
            } catch {
                return
            }
            geschreven += AVAudioFramePosition(n)
            rest -= AVAudioFramePosition(n)
        }
    }

    func pcm(_ sampleBuffer: CMSampleBuffer) -> AVAudioPCMBuffer? {
        guard let beschrijving = CMSampleBufferGetFormatDescription(sampleBuffer),
              let asbd = CMAudioFormatDescriptionGetStreamBasicDescription(beschrijving) else { return nil }
        var streamBeschrijving = asbd.pointee
        guard let bronFormaat = AVAudioFormat(streamDescription: &streamBeschrijving) else { return nil }
        let frames = AVAudioFrameCount(CMSampleBufferGetNumSamples(sampleBuffer))
        guard frames > 0, let bron = AVAudioPCMBuffer(pcmFormat: bronFormaat, frameCapacity: frames) else {
            return nil
        }
        bron.frameLength = frames
        let status = CMSampleBufferCopyPCMDataIntoAudioBufferList(
            sampleBuffer, at: 0, frameCount: Int32(frames), into: bron.mutableAudioBufferList)
        guard status == noErr else { return nil }
        if bronFormaat == doelFormaat {
            return bron
        }

        // Ander formaat dan gevraagd (bijvoorbeeld stereo of 48 kHz): omzetten.
        if converter == nil || converterBron != bronFormaat {
            converter = AVAudioConverter(from: bronFormaat, to: doelFormaat)
            converterBron = bronFormaat
        }
        guard let converter = converter else { return nil }
        let capaciteit = AVAudioFrameCount(Double(frames) * doelFormaat.sampleRate / bronFormaat.sampleRate) + 64
        guard let uit = AVAudioPCMBuffer(pcmFormat: doelFormaat, frameCapacity: capaciteit) else { return nil }
        var gegeven = false
        var conversieFout: NSError?
        _ = converter.convert(to: uit, error: &conversieFout) { _, invoerStatus in
            if gegeven {
                invoerStatus.pointee = .noDataNow
                return nil
            }
            gegeven = true
            invoerStatus.pointee = .haveData
            return bron
        }
        if conversieFout != nil || uit.frameLength == 0 {
            return nil
        }
        return uit
    }
}

// MARK: start

let argumenten = CommandLine.arguments

if argumenten.count >= 2 && argumenten[1] == "--check" {
    Task {
        do {
            _ = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
            meld("OK")
            exit(0)
        } catch {
            fout("geen toestemming voor schermopname: \(error.localizedDescription)")
            exit(2)
        }
    }
    dispatchMain()
}

guard argumenten.count >= 2 else {
    fout("gebruik: notulist-audiocap <uitvoer.wav> | --check")
    exit(64)
}

let recorder = Recorder(url: URL(fileURLWithPath: argumenten[1]))
var signaalBronnen: [DispatchSourceSignal] = []
for sig in [SIGINT, SIGTERM] {
    signal(sig, SIG_IGN)
    let bron = DispatchSource.makeSignalSource(signal: sig, queue: .main)
    bron.setEventHandler {
        Task {
            await recorder.stop()
            exit(0)
        }
    }
    bron.resume()
    signaalBronnen.append(bron)
}

Task {
    do {
        try await recorder.start()
    } catch {
        fout("starten mislukt: \(error.localizedDescription)")
        exit(2)
    }
}

dispatchMain()
