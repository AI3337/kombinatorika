// Распознавание страницы встроенным движком macOS (Vision — то же, что Live Text при копировании из PDF).
// swift ocr.swift in.png out.tsv
// строки: L x y w h текст   — строка целиком (доли страницы, y сверху)
//         G x y w h символ  — символ перед полем хода («4g5», «Exc4»): здесь в книге значок фигуры
import Foundation
import Vision
import AppKit
let url = URL(fileURLWithPath: CommandLine.arguments[1])
guard let img = NSImage(contentsOf: url), let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { exit(1) }
let req = VNRecognizeTextRequest()
req.recognitionLevel = .accurate
req.recognitionLanguages = ["ru-RU", "en-US"]
req.usesLanguageCorrection = false
try VNImageRequestHandler(cgImage: cg).perform([req])
var out = ""
let rx = try NSRegularExpression(pattern: "([^a-hxх\\s.,;:()\\-–—]+)(?=x?[a-h][1-8])")
func box(_ b: CGRect) -> String { String(format: "%.4f\t%.4f\t%.4f\t%.4f", b.minX, 1 - b.maxY, b.width, b.height) }
for o in (req.results ?? []) {
    guard let t = o.topCandidates(1).first else { continue }
    out += "L\t" + box(o.boundingBox) + "\t" + t.string + "\n"
    let s = t.string as NSString
    for m in rx.matches(in: t.string, range: NSRange(location: 0, length: s.length)) {
        let r = m.range(at: 1)
        // слово вокруг значка: до пробелов
        var a = r.location, b = r.location + r.length
        while a > 0 && s.character(at: a - 1) != 32 { a -= 1 }
        while b < s.length && s.character(at: b) != 32 { b += 1 }
        let wr = NSRange(location: a, length: b - a)
        guard let sr = Range(wr, in: t.string), let bb = try? t.boundingBox(for: sr) else { continue }
        // после значка в слове: столько знаков справа приходится на поле/взятие/знаки
        out += "G\t" + box(bb.boundingBox) + "\t" + s.substring(with: wr) + "\t" + String(b - (r.location + r.length)) + "\n"
    }
}
try out.write(toFile: CommandLine.arguments[2], atomically: true, encoding: .utf8)
