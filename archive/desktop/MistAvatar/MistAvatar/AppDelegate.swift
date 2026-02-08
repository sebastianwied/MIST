import Cocoa
import SwiftUI

final class AppDelegate: NSObject, NSApplicationDelegate {
    var avatarPanel: NSPanel!
    var chatPanel: NSPanel!

    func applicationDidFinishLaunching(_ notification: Notification) {
        // Hides Dock icon; comment this out if you want a normal app
        NSApp.setActivationPolicy(.accessory)

        avatarPanel = makeAvatarPanel()
        chatPanel = makeChatPanel()

        avatarPanel.makeKeyAndOrderFront(nil)
    }

    private func makeAvatarPanel() -> NSPanel {
        let contentView = AvatarView { [weak self] in
            self?.toggleChat()
        }

        let host = NSHostingView(rootView: contentView)
        host.frame = NSRect(x: 0, y: 0, width: 56, height: 56)

        let panel = NSPanel(
            contentRect: host.frame,
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )

        panel.contentView = host
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = false
        panel.level = .floating
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.ignoresMouseEvents = false
        panel.isMovableByWindowBackground = true

        if let screen = NSScreen.main {
            let origin = NSPoint(x: screen.frame.maxX - 90, y: screen.frame.maxY - 140)
            panel.setFrameOrigin(origin)
        }

        return panel
    }

    private func makeChatPanel() -> NSPanel {
        let host = NSHostingView(rootView: ChatView())
        host.frame = NSRect(x: 0, y: 0, width: 360, height: 420)

        let panel = NSPanel(
            contentRect: host.frame,
            styleMask: [.titled, .closable, .utilityWindow],
            backing: .buffered,
            defer: false
        )

        panel.title = "MIST"
        panel.contentView = host
        panel.level = .floating
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.isReleasedWhenClosed = false
        panel.orderOut(nil)

        return panel
    }

    private func toggleChat() {
        if chatPanel.isVisible {
            chatPanel.orderOut(nil)
            return
        }

        let a = avatarPanel.frame
        let newOrigin = NSPoint(x: a.minX - 380, y: a.minY - 360)
        chatPanel.setFrameOrigin(newOrigin)

        chatPanel.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }
}
