import SwiftUI

@main
struct MistAvatarApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate

    var body: some Scene {
        Settings {
            EmptyView() // no default window
        }
    }
}
