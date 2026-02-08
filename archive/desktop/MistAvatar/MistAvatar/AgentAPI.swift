import Foundation

struct AgentResponse: Decodable { let reply: String }

func callAgent(text: String) async throws -> String {
    var req = URLRequest(url: URL(string: "http://127.0.0.1:8765/message")!)
    req.httpMethod = "POST"
    req.setValue("application/json", forHTTPHeaderField: "Content-Type")
    req.httpBody = try JSONSerialization.data(withJSONObject: ["text": text])

    let (data, _) = try await URLSession.shared.data(for: req)
    let decoded = try JSONDecoder().decode(AgentResponse.self, from: data)
    return decoded.reply
}
