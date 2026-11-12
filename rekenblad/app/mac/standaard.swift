// Stelt Rekenblad.app in als standaardprogramma voor Excel-bestanden.
// Gebruik: swift standaard.swift /pad/naar/Rekenblad.app [csv]
import AppKit
import UniformTypeIdentifiers

let args = CommandLine.arguments
guard args.count >= 2 else { exit(2) }
let app = URL(fileURLWithPath: args[1])
var types = ["org.openxmlformats.spreadsheetml.sheet", "org.openxmlformats.spreadsheetml.sheet.macroenabled"]
if args.count >= 3 && args[2] == "csv" { types.append("public.comma-separated-values-text") }

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
