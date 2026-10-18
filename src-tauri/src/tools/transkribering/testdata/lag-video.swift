// Lager en film (mov eller mp4) med et svart H.264-videospor FØRST og AAC-lyd fra en wav.
import AVFoundation
import CoreVideo

let args = CommandLine.arguments
let wavURL = URL(fileURLWithPath: args[1])
let outURL = URL(fileURLWithPath: args[2])
let fileType: AVFileType = outURL.pathExtension == "mov" ? .mov : .mp4
try? FileManager.default.removeItem(at: outURL)

let audioAsset = AVURLAsset(url: wavURL)
let sem = DispatchSemaphore(value: 0)
var audioTrack: AVAssetTrack!
var duration: CMTime = .zero
Task {
    audioTrack = try! await audioAsset.loadTracks(withMediaType: .audio).first!
    duration = try! await audioAsset.load(.duration)
    sem.signal()
}
sem.wait()

let writer = try! AVAssetWriter(outputURL: outURL, fileType: fileType)
let vIn = AVAssetWriterInput(mediaType: .video, outputSettings: [
    AVVideoCodecKey: AVVideoCodecType.h264, AVVideoWidthKey: 160, AVVideoHeightKey: 120])
let adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: vIn, sourcePixelBufferAttributes: [
    kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA, kCVPixelBufferWidthKey as String: 160, kCVPixelBufferHeightKey as String: 120])
let aIn = AVAssetWriterInput(mediaType: .audio, outputSettings: [
    AVFormatIDKey: kAudioFormatMPEG4AAC, AVSampleRateKey: 44100, AVNumberOfChannelsKey: 2, AVEncoderBitRateKey: 128000])
writer.add(vIn)   // video first
writer.add(aIn)
writer.startWriting()
writer.startSession(atSourceTime: .zero)

// Video: 10 fps svart, lyd fra wav. Begge mates via requestMediaDataWhenReady.
let fps: Int32 = 10
let nFrames = Int(CMTimeGetSeconds(duration) * Double(fps)) + 1
var pb: CVPixelBuffer?
CVPixelBufferCreate(nil, 160, 120, kCVPixelFormatType_32BGRA, nil, &pb)
CVPixelBufferLockBaseAddress(pb!, [])
memset(CVPixelBufferGetBaseAddress(pb!), 0, CVPixelBufferGetDataSize(pb!))
CVPixelBufferUnlockBaseAddress(pb!, [])
let reader = try! AVAssetReader(asset: audioAsset)
let rOut = AVAssetReaderTrackOutput(track: audioTrack, outputSettings: [AVFormatIDKey: kAudioFormatLinearPCM])
reader.add(rOut)
reader.startReading()
let group = DispatchGroup()
group.enter(); group.enter()
var frame = 0
vIn.requestMediaDataWhenReady(on: DispatchQueue(label: "v")) {
    while vIn.isReadyForMoreMediaData {
        if frame >= nFrames { vIn.markAsFinished(); group.leave(); return }
        adaptor.append(pb!, withPresentationTime: CMTime(value: CMTimeValue(frame), timescale: fps))
        frame += 1
    }
}
aIn.requestMediaDataWhenReady(on: DispatchQueue(label: "a")) {
    while aIn.isReadyForMoreMediaData {
        guard let sb = rOut.copyNextSampleBuffer() else { aIn.markAsFinished(); group.leave(); return }
        aIn.append(sb)
    }
}
group.wait()
writer.finishWriting { sem.signal() }
sem.wait()
print(writer.status == .completed ? "ok" : "failed: \(String(describing: writer.error))")
