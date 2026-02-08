import SwiftUI
import Combine

struct ChatMessage: Identifiable {
    let id = UUID()
    let role: String   // "user" or "agent"
    let text: String
}

@MainActor
final class ChatModel: ObservableObject {
    @Published var messages: [ChatMessage] = []
    @Published var input: String = ""

    func send() {
        let trimmed = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        input = ""

        messages.append(ChatMessage(role: "user", text: trimmed))

        Task {
            do {
                let reply = try await callAgent(text: trimmed)
                messages.append(ChatMessage(role: "agent", text: reply))
            } catch {
                messages.append(ChatMessage(role: "agent",
                                            text: "Error contacting agent: \(error.localizedDescription)"))
            }
        }
    }
}

struct ChatView: View {
    @StateObject private var model = ChatModel()

    var body: some View {
        VStack(spacing: 12) {
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: 10) {
                        ForEach(model.messages) { m in
                            HStack {
                                if m.role == "user" { Spacer() }
                                Text(m.text)
                                    .padding(10)
                                    .background(m.role == "user"
                                                ? Color.blue.opacity(0.2)
                                                : Color.gray.opacity(0.2))
                                    .clipShape(RoundedRectangle(cornerRadius: 14))
                                if m.role == "agent" { Spacer() }
                            }
                            .id(m.id)
                        }
                    }
                    .padding(.top, 10)
                }
                .onChange(of: model.messages.count) { _ in
                    if let last = model.messages.last {
                        proxy.scrollTo(last.id, anchor: .bottom)
                    }
                }
            }

            HStack {
                TextField("Message MIST…", text: $model.input)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { model.send() }

                Button("Send") { model.send() }
            }
        }
        .padding(12)
        .frame(minWidth: 360, minHeight: 420)
    }
}
