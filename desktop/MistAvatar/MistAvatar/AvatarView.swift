import SwiftUI

struct AvatarView: View {
    let onTap: () -> Void

    private var avatarImage: NSImage? {
        let realHome = String(cString: getpwuid(getuid())!.pointee.pw_dir)
        let path = "\(realHome)/Master/MIST/data/config/avatar.png"
        return NSImage(contentsOfFile: path)
    }

    var body: some View {
        ZStack {
            if let img = avatarImage {
                Image(nsImage: img)
                    .resizable()
                    .scaledToFill()
                    .clipShape(Circle())
                    .overlay(Circle().stroke(Color.white.opacity(0.35), lineWidth: 2))
                    .shadow(radius: 6)
            } else {
                Diamond()
                    .fill(Color(red: 0.2, green: 0.7, blue: 1.0).opacity(0.95))
                    .overlay(Diamond().stroke(Color.white.opacity(0.35), lineWidth: 2))
                    .shadow(radius: 6)
            }
        }
        .frame(width: 44, height: 44)
        .padding(6)
        .contentShape(Rectangle())
        .onTapGesture { onTap() }
    }
}

struct Diamond: Shape {
    func path(in rect: CGRect) -> Path {
        var p = Path()
        p.move(to: CGPoint(x: rect.midX, y: rect.maxY))
        p.addLine(to: CGPoint(x: rect.maxX, y: rect.midY))
        p.addLine(to: CGPoint(x: rect.midX, y: rect.minY))
        p.addLine(to: CGPoint(x: rect.minX, y: rect.midY))
        p.closeSubpath()
        return p
    }
}
