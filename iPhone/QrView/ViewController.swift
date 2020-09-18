//
//  ViewController.swift
//  QrView
//
//  Created by Conner Ward on 7/27/20.
//  Copyright © 2020 Conner Ward. All rights reserved.
//

import UIKit
import AVFoundation

struct Item: Codable, Identifiable {
    public var id: Int
    public var title: String
    public var completed: Bool
}

class ViewController: UIViewController, AVCaptureMetadataOutputObjectsDelegate {
    var captureSession: AVCaptureSession!
    var previewLayer: AVCaptureVideoPreviewLayer!
    @IBOutlet weak var mylabel: UILabel!
    @IBOutlet weak var previewView: UIView!
    
    
    override func viewDidLoad() {
        super.viewDidLoad()
        self.mylabel.text = "Scanning..."
        // Get an instance of the AVCaptureDevice class to initialize a
        // device object and provide the video as the media type parameter
        guard let captureDevice = AVCaptureDevice.default(for: AVMediaType.video) else {
            fatalError("No video device found")
        }
                              
        do {
            // Get an instance of the AVCaptureDeviceInput class using the previous deivce object
            let input = try AVCaptureDeviceInput(device: captureDevice)
                   
            // Initialize the captureSession object
            captureSession = AVCaptureSession()
                   
            // Set the input device on the capture session
            captureSession.addInput(input)
                   
            // Get an instance of ACCapturePhotoOutput class
            let capturePhotoOutput = AVCapturePhotoOutput()
            capturePhotoOutput.isHighResolutionCaptureEnabled = true
                   
            // Set the output on the capture session
            captureSession.addOutput(capturePhotoOutput)
            captureSession.sessionPreset = .high
                   
            // Initialize a AVCaptureMetadataOutput object and set it as the input device
            let metadataOutput = AVCaptureMetadataOutput()
            captureSession.addOutput(metadataOutput)
                   
            // Set delegate and use the default dispatch queue to execute the call back
            metadataOutput.setMetadataObjectsDelegate(self, queue: DispatchQueue.main)
            metadataOutput.metadataObjectTypes = [.dataMatrix, .qr]
                   
            //Initialise the video preview layer and add it as a sublayer to the viewPreview view's layer
            previewLayer = AVCaptureVideoPreviewLayer(session: captureSession)
            
            previewLayer.frame = view.layer.bounds
            previewLayer.videoGravity = .resizeAspect
            previewLayer.connection?.videoOrientation = .portrait
            self.previewView.layer.addSublayer(previewLayer)

            DispatchQueue.global(qos: .userInitiated).async { //[weak self] in
                self.captureSession.startRunning()
                //Step 13
            }
            
            DispatchQueue.main.async {
                self.previewLayer.frame = self.previewView.bounds
            }
                   
        } catch {
            //If any error occurs, simply print it out
            print(error)
            return
            ;       }
        
    }
    override func viewWillAppear(_ animated: Bool) {
        super.viewWillAppear(animated)

        if (captureSession?.isRunning == false) {
            captureSession.startRunning()
        }
    }

    override func viewWillDisappear(_ animated: Bool) {
        super.viewWillDisappear(animated)

        if (captureSession?.isRunning == true) {
            captureSession.stopRunning()
        }
    }

    func metadataOutput(_ output: AVCaptureMetadataOutput, didOutput metadataObjects: [AVMetadataObject], from connection: AVCaptureConnection) {
        captureSession.stopRunning()

        if let metadataObject = metadataObjects.first {
            guard let readableObject = metadataObject as? AVMetadataMachineReadableCodeObject else { return }
            guard let stringValue = readableObject.stringValue else { return }
            AudioServicesPlaySystemSound(SystemSoundID(kSystemSoundID_Vibrate))
            let newStr = String(stringValue.suffix(4))
            self.mylabel.text = newStr
        }

        dismiss(animated: true)
    }

    override var prefersStatusBarHidden: Bool {
        return true
    }

    override var supportedInterfaceOrientations: UIInterfaceOrientationMask {
        return .portrait
    }
}

