import SwiftUI
import WidgetKit

struct TokenCoachWidgetEntryView: View {
    @Environment(\.widgetFamily) var family
    let entry: QuotaEntry

    var body: some View {
        switch family {
        case .systemSmall:
            SmallWidgetView(entry: entry)
        default:
            MediumWidgetView(entry: entry)
        }
    }
}

struct TokenCoachWidget: Widget {
    let kind = "TokenCoachWidget"

    var body: some WidgetConfiguration {
        AppIntentConfiguration(kind: kind, intent: SelectProvidersIntent.self, provider: QuotaProvider()) { entry in
            TokenCoachWidgetEntryView(entry: entry)
        }
        .configurationDisplayName("TokenCoach")
        .description("Claude and ChatGPT quota you have left.")
        .supportedFamilies([.systemSmall, .systemMedium])
    }
}

@main
struct TokenCoachWidgetBundle: WidgetBundle {
    var body: some Widget {
        TokenCoachWidget()
    }
}
