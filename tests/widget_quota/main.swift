import Foundation
let snapshot = UsageSnapshot(version: 1, updatedAt: "2026-10-24T12:00:00Z",
    claude: ClaudeUsage(session: nil, weeklyAll: nil, weeklySonnet: nil, overagesEnabled: nil),
    chatgpt: ChatGPTUsage(rows: [LimitRow(label: "5-hour", pct: 17, resetStr: ""),
        LimitRow(label: "Weekly", pct: 100, resetStr: ""),
        LimitRow(label: "Code Review (5-hour)", pct: 100, resetStr: "")], error: nil),
    claudeCode: ClaudeCodeUsage(todayMessages: 0, weekMessages: 0), activeProviders: nil, barProviders: nil)
let display = AIProvider.chatgpt.displayData(from: snapshot)
precondition(display.mainRemainingPct == 83)
precondition(display.rows[1].remainingPct == 0)
print("Widget session and weekly quota assertions passed")
