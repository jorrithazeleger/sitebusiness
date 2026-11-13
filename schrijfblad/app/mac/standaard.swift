// Stelt Schrijfblad.app in als standaardprogramma voor Word-bestanden.
// Gebruik: swift standaard.swift /pad/naar/Schrijfblad.app [doc]
import AppKit
import UniformTypeIdentifiers

let args = CommandLine.arguments
guard args.count >= 2 else { exit(2) }
let app = URL(fileURLWithPath: args[1])
var types = ["org.openxmlformats.wordprocessingml.document",
             "org.openxmlformats.wordprocessingml.document.macroenabled"]
if args.count >= 3 && args[2] == "doc" { types.append("com.microsoft.word.doc") }

var pending = 0
var failed = false
for id in types {
    guard let type = UTType(id) else { continue }
    pending += 1
    NSWorkspace.shared.setDefaultApplication(at: app, toOpen: type) { error in
        if let error = error {
            FileHandle.standardError.write("\(id): \(error.localizedDescription)\n".data(using: .utf8)!)
            failed = true
        }
        pending -= 1
    }
}
let deadline = Date().addingTimeInterval(60)
while pending > 0 && Date() < deadline {
    RunLoop.main.run(until: Date().addingTimeInterval(0.1))
}
exit(failed || pending > 0 ? 1 : 0)
